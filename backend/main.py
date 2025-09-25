from fastapi import FastAPI, HTTPException, Depends, Request, Response, Cookie
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import redis.asyncio as redis
import httpx
import json
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os




app = FastAPI()

# Конфигурация
load_dotenv()
API_KEY = os.getenv("API_KEY_ACCUWEATHER")
BASE_URL = os.getenv("ACCUWEATHER_BASE_URL")
auth_param = f"Bearer {API_KEY}"
REDIS_URL = "redis://localhost:6379"
WEATHER_CACHE_TTL = 3600  # 1 час в секундах

# Модели данных
class CityAddRequest(BaseModel):
    city_name: str

class WeatherData(BaseModel):
    city_name: str
    city_key: str
    current_weather: Dict[str, Any]
    five_day_forecast: List[Dict[str, Any]]
    last_updated: str

class UserFavoritesResponse(BaseModel):
    user_id: str
    favorites: List[WeatherData]

# Инициализация Redis
async def get_redis():
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    try:
        yield redis_client
    finally:
        await redis_client.close()

# Вспомогательные функции
async def get_or_create_user_id(request: Request, response: Response) -> str:
    """Получить user_id из куки или создать новый"""
    user_id = request.cookies.get("user_id")
    
    if not user_id:
        user_id = str(uuid.uuid4())
        # Устанавливаем куки на 1 год
        response.set_cookie(
            key="user_id", 
            value=user_id, 
            max_age=365*24*60*60,
            httponly=True,
            samesite="lax"
        )
    
    return user_id

async def get_city_key(city_name: str) -> Optional[str]:
    """Получить ключ города из API AccuWeather"""
    url = f"{BASE_URL}/locations/v1/cities/search"
    params = {"apikey": API_KEY, "q": city_name}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                if data:
                    return data[0]['Key']
            return None
        except (httpx.RequestError, httpx.TimeoutException):
            return None

async def get_current_weather(city_key: str) -> Optional[Dict[str, Any]]:
    """Получить текущую погоду для города"""
    url = f"{BASE_URL}/currentconditions/v1/{city_key}"
    params = {"apikey": API_KEY}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                return data[0] if data else None
            return None
        except (httpx.RequestError, httpx.TimeoutException):
            return None

async def get_five_day_forecast(city_key: str) -> Optional[List[Dict[str, Any]]]:
    """Получить прогноз на 5 дней для города"""
    url = f"{BASE_URL}/forecasts/v1/daily/5day/{city_key}"
    params = {"apikey": API_KEY, "metric": True}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                return data.get('DailyForecasts', [])
            return None
        except (httpx.RequestError, httpx.TimeoutException):
            return None

async def get_cached_weather_data(redis_client: redis.Redis, user_id: str, city_name: str) -> Optional[Dict[str, Any]]:
    """Получить кэшированные данные о погоде для города пользователя"""
    cache_key = f"user:{user_id}:city:{city_name.lower()}"
    cached_data = await redis_client.get(cache_key)
    
    if cached_data:
        data = json.loads(cached_data)
        # Проверяем актуальность кэша (1 час)
        last_updated = datetime.fromisoformat(data['last_updated'])
        if datetime.now() - last_updated < timedelta(seconds=WEATHER_CACHE_TTL):
            return data
    
    return None

async def cache_weather_data(redis_client: redis.Redis, user_id: str, city_name: str, 
                           city_key: str, current_weather: Dict[str, Any], 
                           five_day_forecast: List[Dict[str, Any]]):
    """Сохранить данные о погоде в кэш"""
    cache_key = f"user:{user_id}:city:{city_name.lower()}"
    
    weather_data = {
        "city_name": city_name,
        "city_key": city_key,
        "current_weather": current_weather,
        "five_day_forecast": five_day_forecast,
        "last_updated": datetime.now().isoformat()
    }
    
    await redis_client.setex(
        cache_key, 
        WEATHER_CACHE_TTL, 
        json.dumps(weather_data)
    )

async def get_user_favorites(redis_client: redis.Redis, user_id: str) -> List[str]:
    """Получить список избранных городов пользователя"""
    favorites_key = f"user:{user_id}:favorites"
    favorites_json = await redis_client.get(favorites_key)
    
    if favorites_json:
        return json.loads(favorites_json)
    return []

async def save_user_favorites(redis_client: redis.Redis, user_id: str, favorites: List[str]):
    """Сохранить список избранных городов пользователя"""
    favorites_key = f"user:{user_id}:favorites"
    await redis_client.set(favorites_key, json.dumps(favorites))

# Эндпоинты
@app.get("/", response_model=UserFavoritesResponse)
async def get_homepage(
    request: Request,
    response: Response,
    redis_client: redis.Redis = Depends(get_redis)
):
    """Главная страница с избранными городами и погодой"""
    user_id = await get_or_create_user_id(request, response)
    favorites = await get_user_favorites(redis_client, user_id)
    
    weather_data_list = []
    
    for city_name in favorites:
        # Проверяем кэш для каждого города
        cached_data = await get_cached_weather_data(redis_client, user_id, city_name)
        
        if cached_data:
            # Используем кэшированные данные
            weather_data_list.append(WeatherData(**cached_data))
        else:
            # Если данных нет в кэше, получаем из API
            city_key = await get_city_key(city_name)
            if not city_key:
                continue
                
            current_weather = await get_current_weather(city_key)
            five_day_forecast = await get_five_day_forecast(city_key)
            
            if current_weather and five_day_forecast:
                # Сохраняем в кэш
                await cache_weather_data(
                    redis_client, user_id, city_name, city_key,
                    current_weather, five_day_forecast
                )
                
                weather_data = WeatherData(
                    city_name=city_name,
                    city_key=city_key,
                    current_weather=current_weather,
                    five_day_forecast=five_day_forecast,
                    last_updated=datetime.now().isoformat()
                )
                weather_data_list.append(weather_data)
    
    return UserFavoritesResponse(
        user_id=user_id,
        favorites=weather_data_list
    )

@app.post("/favorites/add")
async def add_favorite_city(
    city_data: CityAddRequest,
    request: Request,
    response: Response,
    redis_client: redis.Redis = Depends(get_redis)
):
    """Добавить город в избранное"""
    user_id = await get_or_create_user_id(request, response)
    city_name = city_data.city_name.strip()
    
    if not city_name:
        raise HTTPException(status_code=400, detail="City name is required")
    
    # Получаем текущий список избранных городов
    favorites = await get_user_favorites(redis_client, user_id)
    
    if city_name.lower() in [city.lower() for city in favorites]:
        raise HTTPException(status_code=400, detail="City already in favorites")
    
    # Проверяем кэш перед запросом к API
    cached_data = await get_cached_weather_data(redis_client, user_id, city_name)
    
    if cached_data:
        # Используем кэшированные данные
        city_key = cached_data['city_key']
        current_weather = cached_data['current_weather']
        five_day_forecast = cached_data['five_day_forecast']
    else:
        # Получаем данные из API
        city_key = await get_city_key(city_name)
        if not city_key:
            raise HTTPException(status_code=404, detail="City not found")
        
        current_weather = await get_current_weather(city_key)
        five_day_forecast = await get_five_day_forecast(city_key)
        
        if not current_weather or not five_day_forecast:
            raise HTTPException(status_code=500, detail="Failed to get weather data")
        
        # Сохраняем в кэш
        await cache_weather_data(
            redis_client, user_id, city_name, city_key,
            current_weather, five_day_forecast
        )
    
    # Добавляем город в избранное
    favorites.append(city_name)
    await save_user_favorites(redis_client, user_id, favorites)
    
    return {
        "message": "City added to favorites",
        "city_name": city_name,
        "user_id": user_id
    }

@app.delete("/favorites/remove/{city_name}")
async def remove_favorite_city(
    city_name: str,
    request: Request,
    response: Response,
    redis_client: redis.Redis = Depends(get_redis)
):
    """Удалить город из избранного"""
    user_id = await get_or_create_user_id(request, response)
    
    # Получаем текущий список избранных городов
    favorites = await get_user_favorites(redis_client, user_id)
    
    # Находим город (case-insensitive)
    city_to_remove = None
    for city in favorites:
        if city.lower() == city_name.lower():
            city_to_remove = city
            break
    
    if not city_to_remove:
        raise HTTPException(status_code=404, detail="City not found in favorites")
    
    # Удаляем город из списка избранных
    favorites.remove(city_to_remove)
    await save_user_favorites(redis_client, user_id, favorites)
    
    # Удаляем кэшированные данные о погоде
    cache_key = f"user:{user_id}:city:{city_to_remove.lower()}"
    await redis_client.delete(cache_key)
    
    return {
        "message": "City removed from favorites",
        "city_name": city_to_remove,
        "user_id": user_id
    }

@app.get("/favorites/list")
async def get_favorites_list(
    request: Request,
    response: Response,
    redis_client: redis.Redis = Depends(get_redis)
):
    """Получить список избранных городов (без погодных данных)"""
    user_id = await get_or_create_user_id(request, response)
    favorites = await get_user_favorites(redis_client, user_id)
    
    return {
        "user_id": user_id,
        "favorites": favorites
    }

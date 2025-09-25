from fastapi import HTTPException
import os
from typing import Optional

from accuweather import get_city, get_weather_by_city_id, get_weather_by_city_name

import httpx
import redis
import json
import time
from fastapi import FastAPI, Cookie, Response, Request

# Подключение к Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

app = FastAPI()


def get_user_cities(user_id: str) -> list:
    """Получить список городов пользователя"""
    cities_json = redis_client.get(f"user:{user_id}:cities")
    if cities_json:
        return json.loads(cities_json)
    return []

def save_user_city(user_id: str, city: str):
    """Добавить город в список пользователя"""
    cities = get_user_cities(user_id)
    if city not in cities:
        cities.append(city)
        # Сохраняем только последние 10 городов
        cities = cities[-10:]
        redis_client.setex(
            f"user:{user_id}:cities", 
            86400 * 30,  # 30 дней
            json.dumps(cities)
        )

def get_cached_weather_redis(city: str) -> Optional[dict]:
    """Получить погоду из кэша Redis"""
    cached = redis_client.get(f"weather:{city.lower()}")
    if cached:
        return json.loads(cached)
    return None

def get_cached_forecast_redis(city: str) -> Optional[dict]:
    """Получить погоду из кэша Redis"""
    cached = redis_client.get(f"forecast:{city.lower()}")
    if cached:
        return json.loads(cached)
    return None

def set_cached_weather_redis(city: str, data: dict, expire: int = 300):
    """Сохранить погоду в кэш Redis"""
    redis_client.setex(
        f"weather:{city.lower()}",
        expire,
        json.dumps(data)
    )

def set_cached_forecast_redis(city: str, data: dict, expire: int = 300):
    """Сохранить погоду в кэш Redis"""
    redis_client.setex(
        f"forecast:{city.lower()}",
        expire,
        json.dumps(data)
    )

def get_or_create_user_id(request: Request, response: Response) -> str:
    """Получить или создать ID пользователя через cookies"""
    user_id = request.cookies.get("user_id")
    if not user_id:
        import uuid
        user_id = str(uuid.uuid4())
        response.set_cookie(key="user_id", value=user_id, max_age=86400 * 30)
    return user_id


@app.get("/")
async def home(request: Request, response: Response):
    """Главная страница с погодой для избранных городов пользователя"""
    user_id = get_or_create_user_id(request, response)
    user_cities = get_user_cities(user_id)
    
    weather_data = []
    for city in user_cities:
        # Пытаемся получить из кэша
        cached_weather = get_cached_weather_redis(city)
        if cached_weather:
            weather_data.append({
                "city": city,
                "data": cached_weather,
                "source": "cache"
            })
        else:
            # Если нет в кэше, можно запросить у API
            weather_data.append({
                "city": city,
                "data": None,
                "source": "need_update"
            })
    
    return {
        "user_id": user_id,
        "favorite_cities": weather_data
    }

# @app.post("/weather/add_city/{city}")
# async def add_city(city: str, request: Request, response: Response):
#     user_id = get_or_create_user_id(request, response)


@app.get("/weather/{city}")
async def get_weather(city: str, request: Request, response: Response):
    user_id = get_or_create_user_id(request, response)
    
    # Сохраняем город в истории пользователя
    save_user_city(user_id, city)
    
    # Проверяем кэш
    cached_weather = get_cached_weather_redis(city)
    if cached_weather:
        return {
            "source": "cache", 
            "data": cached_weather,
            "user_cities": get_user_cities(user_id)
        }
    
    # Запрос к API
    data = await get_weather_by_city_name(city_name=city)

    set_cached_weather_redis(city=city, data=data)
    
    return {
        "source": "api", 
        city: data,
        "user_cities": get_user_cities(user_id)
    }


@app.get("/weather")
async def get_weather_all(request: Request, response: Response):
    user_id = get_or_create_user_id(request, response)
    res = {}
    cities = get_user_cities(user_id=get_or_create_user_id(request, response))
    for city in get_user_cities(user_id=user_id):
        if city in cities:
            res[city] = get_cached_weather_redis(city=city)
        else:
            data = await get_weather_by_city_name(city)
            res[city] = data
    return res


@app.get("/user/cities")
async def get_user_cities_route(request: Request, response: Response):
    """Получить список городов пользователя"""
    user_id = get_or_create_user_id(request, response)
    return {"cities": get_user_cities(user_id)}


@app.delete("/user/cities/{city}")
async def remove_city(city: str, request: Request, response: Response):
    """Удалить город из списка пользователя"""
    user_id = get_or_create_user_id(request, response)
    cities = get_user_cities(user_id)
    if city in cities:
        cities.remove(city)
        redis_client.setex(
            f"user:{user_id}:cities", 
            86400 * 30,
            json.dumps(cities)
        )
    return {"message": "Город удален", "cities": cities}


@app.get("/forecast/7day/{city}")
async def get_forecast7day(city: str, request: Request, response: Response):
    user_id = get_or_create_user_id(request=request, response=response)
    cities = get_user_cities(user_id)
    if city in cities:
        forecast = get_cached_forecast_redis(city)
        if not forecast:
            res = await get_forecast7day(city)
            return res
        return forecast







# from fastapi import FastAPI

# from accuweather import get_city, get_weather_by_city_id, get_weather_by_city_name


# app = FastAPI()


# @app.get("/")
# def main():
#     return {"hello": "world"}


# cities = []

# @app.get("/weather_by_city_name/{city}")
# async def weather_by_city_name(city: str):
#     return await get_weather_by_city_name(city_name=city)

# @app.post("/cities_list_append/{name}")
# async def append_cities_list(name: str):
#     city_id = await get_city(city_name=name)
#     if city_id:
#         cities.append(name)
#     return cities

# @app.get("/get_weather")
# async def get_weather_of_all_cities():
#     search_cities = cities
#     data = {}
#     for city in search_cities:
#         res = await get_weather_by_city_name(city_name=city)
#         data[city] = res

#     return data
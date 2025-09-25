import asyncio
from fastapi import HTTPException
from dotenv import load_dotenv
import httpx
import os


load_dotenv()
API_URL_BASE = os.getenv("API_URL_BASE")
API_KEY = os.getenv("API_KEY_ACCUWEATHER")
auth_param = f"Bearer {API_KEY}"


async def get_city(city_name: str) -> int:
    """Получить locationKey города по названию для Accuweather API"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            url=f"https://dataservice.accuweather.com/locations/v1/cities/search?q={city_name}",
            headers={
                "Authorization": auth_param
            })
        data = {
            "city_name": response.json()[0]['LocalizedName'],
            "city_id": response.json()[0]['Key']
        }
        
        return data['city_id']


async def get_weather_by_city_name(city_name: str):
    async with httpx.AsyncClient() as client:
        city_id = await get_city(city_name=city_name)
        response = await client.get(
            url=f"https://dataservice.accuweather.com/currentconditions/v1/{city_id}",
            headers={
                "Authorization": auth_param
            })
        return response.json()
    
async def get_weather_by_city_id(city_id: int):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            url=f"https://dataservice.accuweather.com/currentconditions/v1/{city_id}",
            headers={
                "Authorization": auth_param
            })
        return response.json()


async def forecast5days(city_id: int):
    """Получить прогноз погоды города по названию"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            url=f"https://dataservice.accuweather.com/forecasts/v1/daily/5day/{city_id}",
            headers={
                "Authorization": auth_param
            })
        return response.json()


async def main():
    # result = await get_city(city_name="Moscow")
    result = await get_weather_by_city_name(city_name="Moscow")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
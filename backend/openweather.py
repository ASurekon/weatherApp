import asyncio
from fastapi import HTTPException
from dotenv import load_dotenv
import httpx
import os


load_dotenv()
API_URL_BASE = os.getenv("API_URL_BASE")
API_KEY = os.getenv("API_KEY_OPENWEATHER")
params1 = {
        'lat': 44.34,
        'lon': 10.99,
        'appid': API_KEY,
        'units': 'metric',
        'lang': 'ru'
    }

async def get_weather(params: dict):
    async with httpx.AsyncClient() as client:
            try:
                # response = await client.get(API_URL_BASE, params=params)
                url = f"https://api.openweathermap.org/data/2.5/weather?lat=44.34&lon=10.99&appid={API_KEY}"
                response = await client.get(url=url)
                response.raise_for_status()  # Вызовет исключение для статусов 4xx/5xx

                data = response.json()

                # Форматируем ответ, оставляя только нужные данные
                # weather_data = {
                    
                # }

                # Сохраняем в кеш на 10 минут (в секундах)
                # В реальном приложении используйте Redis или Memcached
                # weather_cache[city] = weather_data
                # await asyncio.sleep(600)  # Не делайте так! Это заблокирует весь сервер.
                # Лучше использовать TTLCache из библиотеки cachetools

                return {
                    'success': True,
                    'data': data
                }

            except httpx.HTTPStatusError as e:
                # Обрабатываем ошибки от погодного API
                if e.response.status_code == 404:
                    return {"detail": "Город не найден"}
                elif e.response.status_code == 401:
                    return {"detail": "Неверный API-ключ OpenWeatherMap"}
                else:
                    return {"detail": "Ошибка при запросе к сервису погоды"}
            except Exception as e:
                return {"error": e}


async def main():

    weather_data = await get_weather(params=params1)
    print(weather_data)


if __name__ == "__main__":
    asyncio.run(main())
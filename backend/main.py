from fastapi import FastAPI

from accuweather import get_city, get_weather_by_city_id, get_weather_by_city_name


app = FastAPI()


@app.get("/")
def main():
    return {"hello": "world"}


cities = []

@app.get("/weather_by_city_name/{city}")
async def weather_by_city_name(city: str):
    return await get_weather_by_city_name(city_name=city)

@app.post("/cities_list_append/{name}")
async def append_cities_list(name: str):
    city_id = await get_city(city_name=name)
    if city_id:
        cities.append(name)
    return cities

@app.get("/get_weather")
async def get_weather_of_all_cities():
    search_cities = cities
    data = {}
    for city in search_cities:
        res = await get_weather_by_city_name(city_name=city)
        data[city] = res

    return data
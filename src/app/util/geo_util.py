import math

# 지구 반지름 (km). 하버사인 공식에서 쓰는 평균값
EARTH_RADIUS_KM = 6371.0

# 위도 1도의 길이 (km) = 지구 둘레 / 360
KM_PER_LAT_DEGREE = 2 * math.pi * EARTH_RADIUS_KM / 360


# 두 지점(위도·경도) 사이의 거리 (km) - 하버사인 공식
# - 지구를 구로 보고 계산한다. 10km 안팎의 거리에서는 오차가 수 m 수준이라 병원 찾기에 충분하다.
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


# 중심에서 반경 radius_km을 감싸는 위도·경도 사각형 (min_lat, max_lat, min_lon, max_lon)
# - PostGIS가 없어서 SQL에서는 이 사각형으로 대략 거르고, 정확한 거리는 haversine_km로 다시 잰다.
# - 경도 1도의 길이는 위도가 높을수록 짧아진다 (적도에서 약 111km, 위도 37도에서 약 89km).
def bounding_box(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    d_lat = radius_km / KM_PER_LAT_DEGREE
    d_lon = radius_km / (KM_PER_LAT_DEGREE * max(math.cos(math.radians(lat)), 1e-6))
    return lat - d_lat, lat + d_lat, lon - d_lon, lon + d_lon

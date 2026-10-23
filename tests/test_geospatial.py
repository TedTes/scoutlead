from sqlalchemy import create_engine, literal, select

from shared.geospatial import (
    haversine_distance_km,
    haversine_distance_km_expression,
)


def test_sql_haversine_matches_python_for_short_and_antipodal_distances() -> None:
    engine = create_engine("sqlite:///:memory:")

    with engine.connect() as connection:
        for target in [(43.6532, -79.3832), (-43.6532, 100.6168)]:
            expression = haversine_distance_km_expression(
                center_latitude=43.6532,
                center_longitude=-79.3832,
                latitude=literal(target[0]),
                longitude=literal(target[1]),
            )
            actual = connection.scalar(select(expression))
            expected = haversine_distance_km(
                43.6532,
                -79.3832,
                target[0],
                target[1],
            )
            assert actual is not None
            assert abs(float(actual) - expected) < 0.001

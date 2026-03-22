"""
Script de génération des fixtures Parquet pour les tests.

À placer dans: tests/fixtures/parquet/generate_fixtures.py

Usage:
    cd tests/fixtures/parquet
    python generate_fixtures.py

Author: Hydra Team
Date: Février 2026
"""

import pandas as pd
from pathlib import Path
from datetime import datetime, date


def generate_fixtures():
    """Génère les fichiers fixtures Parquet."""
    
    # Créer le répertoire si nécessaire
    fixtures_dir = Path(__file__).parent
    fixtures_dir.mkdir(exist_ok=True)
    
    print(f"📁 Génération fixtures dans: {fixtures_dir}")
    
    # ============================================================
    # Fixture 1: users.parquet (données simples)
    # ============================================================
    
    users_data = {
        "id": [1, 2, 3, 4, 5],
        "name": ["Alice", "Bob", "Charlie", "Diana", "Eve"],
        "email": ["alice@test.com", "bob@test.com", "charlie@test.com", "diana@test.com", "eve@test.com"],
        "age": [25, 30, 35, 28, 42],
        "salary": [50000.50, 60000.75, 75000.00, 55000.25, 80000.00],
        "is_active": [True, True, False, True, True],
        "created_at": [
            datetime(2024, 1, 1, 10, 0, 0),
            datetime(2024, 1, 2, 11, 0, 0),
            datetime(2024, 1, 3, 12, 0, 0),
            datetime(2024, 1, 4, 13, 0, 0),
            datetime(2024, 1, 5, 14, 0, 0),
        ]
    }
    
    df_users = pd.DataFrame(users_data)
    users_path = fixtures_dir / "users.parquet"
    df_users.to_parquet(users_path, compression="snappy", index=False)
    print(f"✅ users.parquet créé ({len(df_users)} lignes)")
    
    # ============================================================
    # Fixture 2: orders.parquet (données volumineuses)
    # ============================================================
    
    orders_data = {
        "order_id": list(range(1, 101)),
        "user_id": [i % 5 + 1 for i in range(100)],
        "product": [f"Product-{i % 10}" for i in range(100)],
        "quantity": [(i % 10) + 1 for i in range(100)],
        "price": [10.99 + (i * 0.5) for i in range(100)],
        "order_date": [date(2024, 1, (i % 28) + 1) for i in range(100)],
        "status": ["completed" if i % 3 == 0 else "pending" for i in range(100)]
    }
    
    df_orders = pd.DataFrame(orders_data)
    orders_path = fixtures_dir / "orders.parquet"
    df_orders.to_parquet(orders_path, compression="gzip", index=False)
    print(f"✅ orders.parquet créé ({len(df_orders)} lignes, compression gzip)")
    
    # ============================================================
    # Fixture 3: products.parquet (compression brotli)
    # ============================================================
    
    products_data = {
        "product_id": [1, 2, 3, 4, 5],
        "product_name": ["Laptop", "Mouse", "Keyboard", "Monitor", "Webcam"],
        "category": ["Electronics", "Accessories", "Accessories", "Electronics", "Accessories"],
        "price": [999.99, 29.99, 79.99, 299.99, 59.99],
        "stock": [50, 200, 150, 75, 100],
        "available": [True, True, False, True, True]
    }
    
    df_products = pd.DataFrame(products_data)
    products_path = fixtures_dir / "products.parquet"
    df_products.to_parquet(products_path, compression="brotli", index=False)
    print(f"✅ products.parquet créé ({len(df_products)} lignes, compression brotli)")
    
    # ============================================================
    # Fixture 4: empty.parquet (fichier vide avec schéma)
    # ============================================================
    
    import pyarrow as pa
    import pyarrow.parquet as pq
    
    schema = pa.schema([
        ("id", pa.int64()),
        ("name", pa.string()),
        ("value", pa.float64())
    ])
    
    empty_table = pa.Table.from_pydict(
        {"id": [], "name": [], "value": []},
        schema=schema
    )
    
    empty_path = fixtures_dir / "empty.parquet"
    pq.write_table(empty_table, empty_path, compression="snappy")
    print(f"✅ empty.parquet créé (0 lignes avec schéma)")
    
    # ============================================================
    # Fixture 5: large.parquet (10k lignes pour tests performance)
    # ============================================================
    
    large_data = {
        "id": list(range(1, 10001)),
        "value": [i * 1.5 for i in range(1, 10001)],
        "category": [f"cat_{i % 100}" for i in range(10000)],
        "flag": [i % 2 == 0 for i in range(10000)]
    }
    
    df_large = pd.DataFrame(large_data)
    large_path = fixtures_dir / "large.parquet"
    df_large.to_parquet(large_path, compression="snappy", index=False)
    print(f"✅ large.parquet créé ({len(df_large)} lignes)")
    
    # ============================================================
    # Fixture 6: sales.parquet (pour tests de transformation)
    # ============================================================
    
    sales_data = {
        "sale_id": list(range(1, 21)),
        "region": ["North", "South", "East", "West"] * 5,
        "amount": [100 + (i * 50) for i in range(20)],
        "month": ["2024-01", "2024-02", "2024-03", "2024-04"] * 5
    }
    
    df_sales = pd.DataFrame(sales_data)
    sales_path = fixtures_dir / "sales.parquet"
    df_sales.to_parquet(sales_path, compression="snappy", index=False)
    print(f"✅ sales.parquet créé ({len(df_sales)} lignes)")
    
    # ============================================================
    # Résumé
    # ============================================================
    
    print("\n📊 Résumé des fixtures générées:")
    print(f"  - users.parquet: {len(df_users)} lignes (snappy)")
    print(f"  - orders.parquet: {len(df_orders)} lignes (gzip)")
    print(f"  - products.parquet: {len(df_products)} lignes (brotli)")
    print(f"  - empty.parquet: 0 lignes (snappy)")
    print(f"  - large.parquet: {len(df_large)} lignes (snappy)")
    print(f"  - sales.parquet: {len(df_sales)} lignes (snappy)")
    print(f"\n✅ Toutes les fixtures créées dans: {fixtures_dir}")


if __name__ == "__main__":
    generate_fixtures()
from app.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    hooks = db.execute(text("SELECT id, name, parent_id FROM categories WHERE name ILIKE 'Hooks'")).fetchall()
    print(f'Categories named Hooks: {list(hooks)}')

    if hooks:
        hook_id = hooks[0][0]
        count_parent = db.execute(text(
            "SELECT COUNT(DISTINCT pc.product_id) FROM product_categories pc "
            "JOIN categories c ON c.id = pc.category_id "
            "WHERE c.name = 'Hooks' AND c.parent_id IS NULL"
        )).scalar()
        print(f'Products with Hooks as PARENT category (parent_id IS NULL): {count_parent}')

        rows = db.execute(text(
            "SELECT p.name, c.name, c.parent_id FROM products p "
            "JOIN product_categories pc ON pc.product_id = p.id "
            "JOIN categories c ON c.id = pc.category_id "
            "WHERE p.id IN ("
            "  SELECT DISTINCT pc2.product_id FROM product_categories pc2 "
            "  JOIN categories c2 ON c2.id = pc2.category_id WHERE c2.name = 'Hooks'"
            ") LIMIT 20"
        )).fetchall()
        print('Sample product-category rows for Hooks products:')
        for r in rows:
            print(f'  {r[0][:40]:40s} | {r[1]:30s} | parent_id={r[2]}')
finally:
    db.close()

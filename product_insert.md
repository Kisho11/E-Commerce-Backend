# Product Bulk Insert — ElmShelf.xlsx to PostgreSQL

This document explains how to load products from an Excel file into the PostgreSQL database using the `seed_products.py` script.

---

## What the script does

- Clears all existing products, categories, inventory, and variants from the database
- Reads every sheet in the Excel file (except the empty `Sheet3` template)
- Creates a hierarchical category tree (Category → Subcategory)
- Inserts each product with price, description, dimensions, and colour variants
- Creates one `inventory` row per product (stock starts at 0)
- Auto-generates a unique slug and SKU (`ELM-00001`, `ELM-00002`, …) for every product

---

## Prerequisites

### 1. Python & virtual environment

Make sure the backend virtual environment is active and `openpyxl` is installed:

```bash
# From E-Commerce-Backend/
venv\Scripts\python.exe -m pip install openpyxl
```

### 2. PostgreSQL running

The database must be running and the tables must already exist (created by SQLAlchemy on app startup or via Alembic migrations). Check your `.env` file:

```
DATABASE_URL=postgresql://postgres:password@localhost:5432/furniture_store
```

### 3. Excel file location

Place `ElmShelf.xlsx` in the project root — one level above `E-Commerce-Backend/`:

```
E-Commerce/
├── ElmShelf.xlsx          ← here
└── E-Commerce-Backend/
    └── seed_products.py
```

---

## How to run

Open a terminal in `E-Commerce-Backend/` and run:

```bash
venv\Scripts\python.exe seed_products.py
```

To use a custom Excel file path:

```bash
venv\Scripts\python.exe seed_products.py "C:\path\to\YourFile.xlsx"
```

Expected output:

```
Clearing existing product data...
  Done.

Reading: D:\E-Commerce\Application\ElmShelf.xlsx
  [Crisps & Display] 28 products loaded
  [Hooks] 25 products loaded
  ...
  [Shelf Management] 81 products loaded

==================================================
  Total products : 1140
  Total categories: 81
==================================================
```

---

## Excel file format

The script reads all sheets that contain a header row with `Product Name`. Each sheet represents a product category.

### Required column (must exist)

| Column | Description |
|---|---|
| `Product Name` | The product title (rows without this are skipped) |

### Optional columns (used when present)

| Column | Maps to |
|---|---|
| `Category` | Parent category name |
| `Sub category` | Child category name (nested under Category) |
| `Price Range` | `products.price` (min) and `products.sale_price` (max for ranges) |
| `Colour` / `Color` | Creates colour variants if multiple values (e.g. `Black, Silver or Walnut`) |
| `Depth(mm)` / `Length(mm)` | Stored in `additional_information` JSON |
| `Width(mm)` | Stored in `additional_information` JSON |
| `Height(mm)` | Stored in `additional_information` JSON |
| `Weight(kg)` | Stored in `additional_information` JSON |
| `Finish` | Stored in `additional_information` JSON |
| `Size` | Stored in `additional_information` JSON |
| `Main note` | Prepended to product description |
| `Description` | Product description body |
| `Key features` | Appended to product description |
| `What's included` | Stored in `additional_information` JSON |
| `Important Notes` | Stored in `additional_information` JSON |
| `Additional information` | Stored in `additional_information` JSON |

### Price format rules

| Excel value | Result |
|---|---|
| `£221.07` | `price = 221.07`, `sale_price = null` |
| `£14.30 – £28.59` | `price = 14.30`, `sale_price = 28.59` |
| `-` / `--` / `POA` / `TBC` | `price = 0.00`, `sale_price = null` |

When a price range is detected, the original text (e.g. `£14.30 – £28.59`) is also saved inside `additional_information.price_range_text` for display purposes.

### Colour variant rules

If the `Colour` column contains multiple values separated by `,`, `/`, or ` or `, the script:

- Sets `product_type = variable`
- Creates a `ProductVariantGroup` with `attribute = "Color"`
- Creates one `ProductVariant` per colour

Single colour → `product_type = simple`, no variant group created.

---

## Database tables affected

The script deletes and re-inserts data in this order:

| Table cleared | Reason |
|---|---|
| `stock_movements` | References inventory |
| `inventory` | References products |
| `reviews` | References products |
| `order_items` | References products |
| `cart_items` | References products |
| `product_variants` | References variant groups |
| `product_variant_groups` | References products |
| `product_images` | References products |
| `product_categories` | Junction table |
| `products` | Main product table |
| `categories` | Cleared last |

**Users, orders, carts, and addresses are NOT deleted.**

---

## Adding a new Excel sheet

To add more products in a new sheet:

1. Create a new sheet in `ElmShelf.xlsx`
2. Row 1 (optional): group headers (`Basic Details`, `Pricing`, `Description`)
3. Row 2: column headers — must include `Product Name`
4. Row 3 onwards: product data

The script auto-detects the header row (searches first 6 rows for `Product Name`). No code changes needed — just re-run the script.

---

## Re-running / refreshing data

The script is **destructive** — it clears all product data before inserting. To refresh:

```bash
venv\Scripts\python.exe seed_products.py
```

To add new products **without clearing** existing ones, you would need to modify the script to skip the `DELETE` block at the top. Contact the developer to implement an upsert mode.

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'openpyxl'`

```bash
venv\Scripts\python.exe -m pip install openpyxl
```

### `No module named 'app'`

Run the script from the `E-Commerce-Backend/` directory, not from the project root.

### `FileNotFoundError: ElmShelf.xlsx`

Either pass the path explicitly:

```bash
venv\Scripts\python.exe seed_products.py "D:\full\path\to\ElmShelf.xlsx"
```

Or move the file to `E-Commerce\ElmShelf.xlsx` (one level above `E-Commerce-Backend/`).

### `connection refused` / DB errors

Make sure PostgreSQL is running and the `DATABASE_URL` in `.env` is correct.

### Product loaded with `price = 0`

The price cell in the Excel row contained `-`, `--`, `POA`, or was empty. Update the cell with a numeric price and re-run the script.

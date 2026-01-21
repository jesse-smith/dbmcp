-- Test Database Schema Contract
-- Feature: 002-example-notebooks
-- Version: 1.0
-- Purpose: Sample e-commerce database for DBMCP examples
-- Compatible with: SQL Server, SQLite (with minor dialect adjustments)

-- ============================================================================
-- CUSTOMERS TABLE
-- Purpose: Demonstrate basic table with IDENTITY PK and UNIQUE constraint
-- ============================================================================
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    email VARCHAR(255) UNIQUE NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- PRODUCTS TABLE
-- Purpose: Demonstrate DECIMAL types and DEFAULT values
-- ============================================================================
CREATE TABLE products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(200) NOT NULL,
    category VARCHAR(50),
    price DECIMAL(10,2) NOT NULL,
    stock_quantity INTEGER DEFAULT 0
);

-- ============================================================================
-- ORDERS TABLE
-- Purpose: Demonstrate declared FOREIGN KEY and CHECK constraint
-- ============================================================================
CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    order_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) CHECK (status IN ('pending', 'shipped', 'delivered', 'cancelled')),
    total_amount DECIMAL(10,2),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

-- ============================================================================
-- ORDER_ITEMS TABLE
-- Purpose: Demonstrate junction table with multiple declared FKs
-- ============================================================================
CREATE TABLE order_items (
    order_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

-- ============================================================================
-- SHIPPING_ADDRESSES TABLE
-- Purpose: Demonstrate UNDECLARED FK (for relationship inference examples)
-- Note: customer_id intentionally NOT declared as FK
-- ============================================================================
CREATE TABLE shipping_addresses (
    address_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,  -- Undeclared FK to customers
    street VARCHAR(255),
    city VARCHAR(100),
    postal_code VARCHAR(20),
    country VARCHAR(2) DEFAULT 'US'
);

-- ============================================================================
-- PRODUCT_REVIEWS TABLE
-- Purpose: Demonstrate multiple UNDECLARED FKs and rating constraint
-- Note: product_id and customer_id intentionally NOT declared as FKs
-- ============================================================================
CREATE TABLE product_reviews (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,    -- Undeclared FK to products
    customer_id INTEGER NOT NULL,   -- Undeclared FK to customers
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    review_text TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- SAMPLE DATA - CUSTOMERS
-- ============================================================================
INSERT INTO customers (email, first_name, last_name) VALUES
('alice@example.com', 'Alice', 'Anderson'),
('bob@example.com', 'Bob', 'Brown'),
('carol@example.com', 'Carol', 'Clark'),
('dave@example.com', 'Dave', 'Davis'),
('eve@example.com', 'Eve', 'Evans'),
('frank@example.com', 'Frank', 'Foster'),
('grace@example.com', 'Grace', 'Garcia'),
('henry@example.com', 'Henry', 'Harris'),
('iris@example.com', 'Iris', 'Ivanov'),
('jack@example.com', 'Jack', 'Jackson');

-- ============================================================================
-- SAMPLE DATA - PRODUCTS
-- ============================================================================
INSERT INTO products (name, category, price, stock_quantity) VALUES
('Laptop Pro 15"', 'Electronics', 1299.99, 25),
('Wireless Mouse', 'Electronics', 29.99, 150),
('USB-C Cable', 'Electronics', 12.99, 300),
('Desk Chair', 'Furniture', 199.99, 45),
('Standing Desk', 'Furniture', 499.99, 20),
('Monitor 27"', 'Electronics', 349.99, 60),
('Keyboard Mechanical', 'Electronics', 89.99, 80),
('Desk Lamp', 'Furniture', 39.99, 100),
('Notebook Set', 'Office Supplies', 15.99, 200),
('Pen Set', 'Office Supplies', 9.99, 250),
('Coffee Mug', 'Office Supplies', 12.99, 120),
('Water Bottle', 'Office Supplies', 19.99, 90),
('Headphones', 'Electronics', 79.99, 70),
('Webcam HD', 'Electronics', 69.99, 55),
('Backpack', 'Accessories', 49.99, 85),
('Phone Stand', 'Accessories', 24.99, 140),
('Cable Organizer', 'Accessories', 14.99, 180),
('Whiteboard', 'Office Supplies', 59.99, 30),
('Desk Mat', 'Accessories', 29.99, 110),
('Plant Stand', 'Furniture', 34.99, 65);

-- ============================================================================
-- SAMPLE DATA - ORDERS
-- ============================================================================
INSERT INTO orders (customer_id, status, total_amount) VALUES
(1, 'delivered', 1329.98),    -- Alice
(1, 'pending', 199.99),        -- Alice
(2, 'shipped', 549.98),        -- Bob
(3, 'delivered', 89.99),       -- Carol
(3, 'delivered', 369.98),      -- Carol
(4, 'delivered', 79.99),       -- Dave
(5, 'cancelled', 499.99),      -- Eve
(5, 'delivered', 102.98),      -- Eve
(6, 'shipped', 1649.97),       -- Frank
(7, 'delivered', 49.99),       -- Grace
(8, 'pending', 159.97),        -- Henry
(9, 'delivered', 699.98),      -- Iris
(10, 'delivered', 25.98),      -- Jack
(10, 'shipped', 139.98),       -- Jack
(2, 'delivered', 389.97);      -- Bob

-- ============================================================================
-- SAMPLE DATA - ORDER_ITEMS
-- ============================================================================
INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
-- Order 1 (Alice)
(1, 1, 1, 1299.99),
(1, 2, 1, 29.99),
-- Order 2 (Alice)
(2, 4, 1, 199.99),
-- Order 3 (Bob)
(3, 5, 1, 499.99),
(3, 8, 1, 39.99),
(3, 9, 1, 9.99),
-- Order 4 (Carol)
(4, 7, 1, 89.99),
-- Order 5 (Carol)
(5, 6, 1, 349.99),
(5, 3, 1, 12.99),
(5, 16, 1, 6.99),
-- Order 6 (Dave)
(6, 13, 1, 79.99),
-- Order 7 (Eve - cancelled)
(7, 5, 1, 499.99),
-- Order 8 (Eve)
(8, 11, 2, 12.99),
(8, 10, 3, 9.99),
(8, 17, 2, 14.99),
-- Order 9 (Frank)
(9, 1, 1, 1299.99),
(9, 6, 1, 349.99),
-- Order 10 (Grace)
(10, 15, 1, 49.99),
-- Order 11 (Henry)
(11, 12, 2, 19.99),
(11, 11, 3, 12.99),
(11, 19, 2, 29.99),
-- Order 12 (Iris)
(12, 1, 1, 1299.99),
(12, 14, 1, 69.99),
(12, 2, 1, 29.99),
-- Order 13 (Jack)
(13, 10, 1, 9.99),
(13, 3, 2, 12.99),
-- Order 14 (Jack)
(14, 13, 1, 79.99),
(14, 2, 2, 29.99),
-- Order 15 (Bob)
(15, 4, 1, 199.99),
(15, 8, 1, 39.99),
(15, 18, 1, 59.99),
(15, 19, 3, 29.99);

-- ============================================================================
-- SAMPLE DATA - SHIPPING_ADDRESSES
-- Note: customer_id references customers but FK not declared (for inference)
-- ============================================================================
INSERT INTO shipping_addresses (customer_id, street, city, postal_code, country) VALUES
(1, '123 Main St', 'Seattle', '98101', 'US'),
(1, '456 Oak Ave', 'Portland', '97201', 'US'),
(2, '789 Pine Rd', 'San Francisco', '94102', 'US'),
(3, '321 Elm Dr', 'Austin', '78701', 'US'),
(4, '654 Maple Ln', 'Denver', '80202', 'US'),
(5, '987 Cedar Ct', 'Chicago', '60601', 'US'),
(6, '147 Birch Way', 'Boston', '02101', 'US'),
(7, '258 Ash Blvd', 'Miami', '33101', 'US'),
(8, '369 Spruce St', 'Phoenix', '85001', 'US'),
(9, '741 Willow Ave', 'Atlanta', '30301', 'US'),
(10, '852 Poplar Dr', 'Dallas', '75201', 'US'),
(2, '963 Hickory Rd', 'Las Vegas', '89101', 'US');

-- ============================================================================
-- SAMPLE DATA - PRODUCT_REVIEWS
-- Note: product_id and customer_id reference other tables but FKs not declared
-- ============================================================================
INSERT INTO product_reviews (product_id, customer_id, rating, review_text) VALUES
(1, 1, 5, 'Excellent laptop, very fast and great display!'),
(1, 9, 4, 'Good performance but a bit pricey.'),
(2, 1, 5, 'Perfect wireless mouse, very responsive.'),
(2, 10, 4, 'Good mouse, battery life could be better.'),
(3, 13, 5, 'Great cable, works perfectly.'),
(4, 2, 4, 'Comfortable chair, easy to assemble.'),
(4, 15, 5, 'Best chair I''ve ever owned!'),
(5, 3, 3, 'Desk is sturdy but instructions unclear.'),
(6, 5, 5, 'Amazing monitor, colors are vibrant.'),
(7, 4, 5, 'Love this keyboard, typing feels great.'),
(8, 2, 4, 'Nice lamp, adjustable brightness is handy.'),
(8, 15, 5, 'Perfect lighting for my desk.'),
(10, 8, 5, 'Great pens, smooth writing.'),
(11, 8, 4, 'Nice mug, keeps coffee hot.'),
(12, 11, 5, 'Excellent water bottle, no leaks.'),
(13, 6, 5, 'Great headphones, noise cancellation works well.'),
(13, 4, 4, 'Good sound quality, comfortable fit.'),
(14, 12, 4, 'Decent webcam for the price.'),
(15, 7, 5, 'Love this backpack, lots of pockets.'),
(16, 11, 5, 'Perfect phone stand for video calls.'),
(17, 8, 4, 'Good cable organizer, keeps desk tidy.'),
(18, 15, 3, 'Whiteboard is okay, marker erases poorly.'),
(19, 11, 5, 'Great desk mat, nice size.'),
(19, 14, 4, 'Good quality mat, comfortable for wrists.'),
(20, 7, 5, 'Beautiful plant stand, sturdy construction.');

-- ============================================================================
-- VALIDATION QUERIES
-- These queries should be used to verify schema correctness after setup
-- ============================================================================

-- Check table counts
-- Expected: 6 tables
-- SELECT COUNT(*) FROM sqlite_master WHERE type='table';

-- Check declared foreign keys
-- Expected: 3 FKs (orders.customer_id, order_items.order_id, order_items.product_id)
-- SELECT * FROM pragma_foreign_key_list('orders');
-- SELECT * FROM pragma_foreign_key_list('order_items');

-- Check undeclared relationships (should have matching IDs but no FK constraint)
-- Expected: No FK constraints
-- SELECT * FROM pragma_foreign_key_list('shipping_addresses');
-- SELECT * FROM pragma_foreign_key_list('product_reviews');

-- Check data integrity
-- Expected: All foreign key references valid
-- SELECT COUNT(*) FROM shipping_addresses WHERE customer_id NOT IN (SELECT customer_id FROM customers);  -- Should be 0
-- SELECT COUNT(*) FROM product_reviews WHERE customer_id NOT IN (SELECT customer_id FROM customers);     -- Should be 0
-- SELECT COUNT(*) FROM product_reviews WHERE product_id NOT IN (SELECT product_id FROM products);        -- Should be 0

-- ============================================================================
-- NOTES FOR IMPLEMENTERS
-- ============================================================================
-- 1. This schema uses SQLite syntax (AUTOINCREMENT, CURRENT_TIMESTAMP)
-- 2. For SQL Server, replace AUTOINCREMENT with IDENTITY(1,1)
-- 3. For SQL Server, replace CURRENT_TIMESTAMP with GETDATE()
-- 4. Maintain schema version in comments at top when updating
-- 5. Keep sample data realistic and internally consistent
-- 6. Ensure undeclared FKs have naming patterns that inference can detect
--    (e.g., customer_id, product_id naming convention)
-- ============================================================================

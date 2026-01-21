-- Test database schema for dbmcp integration tests
-- This script creates a test database with known relationships for testing
-- FK inference accuracy and metadata retrieval.

-- Create test schemas
IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'sales')
    EXEC('CREATE SCHEMA sales');
GO

IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'hr')
    EXEC('CREATE SCHEMA hr');
GO

-- =============================================================================
-- dbo schema tables (main business entities)
-- =============================================================================

-- Customers table (referenced by Orders)
CREATE TABLE dbo.Customers (
    CustomerID INT IDENTITY(1,1) PRIMARY KEY,
    CustomerName NVARCHAR(100) NOT NULL,
    Email VARCHAR(100),
    Phone VARCHAR(20),
    Status VARCHAR(20) DEFAULT 'Active',
    CreatedDate DATETIME DEFAULT GETDATE(),
    ModifiedDate DATETIME
);

-- Products table (referenced by OrderItems)
CREATE TABLE dbo.Products (
    ProductID INT IDENTITY(1,1) PRIMARY KEY,
    ProductName NVARCHAR(100) NOT NULL,
    SKU VARCHAR(50) UNIQUE,
    CategoryCode VARCHAR(10),
    UnitPrice DECIMAL(10,2),
    IsActive BIT DEFAULT 1
);

-- Categories table (for testing inference with Categories.CategoryCode)
CREATE TABLE dbo.Categories (
    CategoryID INT IDENTITY(1,1) PRIMARY KEY,
    CategoryCode VARCHAR(10) UNIQUE NOT NULL,
    CategoryName NVARCHAR(50) NOT NULL,
    Description NVARCHAR(500)
);

-- Orders table (with declared FK to Customers)
CREATE TABLE dbo.Orders (
    OrderID INT IDENTITY(1,1) PRIMARY KEY,
    CustomerID INT,
    OrderDate DATETIME NOT NULL DEFAULT GETDATE(),
    ShipDate DATETIME,
    Status VARCHAR(20) DEFAULT 'Pending',
    TotalAmount DECIMAL(12,2),
    CONSTRAINT FK_Orders_Customers FOREIGN KEY (CustomerID)
        REFERENCES dbo.Customers(CustomerID)
);

-- OrderItems table (with declared FKs to Orders and Products)
CREATE TABLE dbo.OrderItems (
    OrderItemID INT IDENTITY(1,1) PRIMARY KEY,
    OrderID INT NOT NULL,
    ProductID INT NOT NULL,
    Quantity INT NOT NULL DEFAULT 1,
    UnitPrice DECIMAL(10,2) NOT NULL,
    Discount DECIMAL(5,2) DEFAULT 0,
    CONSTRAINT FK_OrderItems_Orders FOREIGN KEY (OrderID)
        REFERENCES dbo.Orders(OrderID),
    CONSTRAINT FK_OrderItems_Products FOREIGN KEY (ProductID)
        REFERENCES dbo.Products(ProductID)
);

-- =============================================================================
-- Tables for testing UNDECLARED foreign keys (inference targets)
-- =============================================================================

-- ShipmentLog - has CustomerID but NO declared FK
CREATE TABLE dbo.ShipmentLog (
    ShipmentID INT IDENTITY(1,1) PRIMARY KEY,
    OrderNum INT,  -- Similar to OrderID (test name inference)
    CustomerID INT,  -- Should infer to Customers.CustomerID
    ShipDate DATETIME,
    Carrier VARCHAR(50),
    TrackingNumber VARCHAR(100)
);

-- AuditLog - has CustomerID but NO declared FK
CREATE TABLE dbo.AuditLog (
    AuditID INT IDENTITY(1,1) PRIMARY KEY,
    TableName VARCHAR(50),
    RecordID INT,
    Action VARCHAR(20),
    CustomerID INT,  -- Should infer to Customers.CustomerID
    CreatedBy VARCHAR(50),
    CreatedAt DATETIME DEFAULT GETDATE()
);

-- ProductReviews - has ProductID but NO declared FK
CREATE TABLE dbo.ProductReviews (
    ReviewID INT IDENTITY(1,1) PRIMARY KEY,
    ProductID INT,  -- Should infer to Products.ProductID
    CustomerID INT,  -- Should infer to Customers.CustomerID
    Rating INT,
    ReviewText NVARCHAR(MAX),
    ReviewDate DATETIME DEFAULT GETDATE()
);

-- =============================================================================
-- sales schema tables
-- =============================================================================

-- SalesReps table
CREATE TABLE sales.SalesReps (
    SalesRepID INT IDENTITY(1,1) PRIMARY KEY,
    RepName NVARCHAR(100) NOT NULL,
    Region VARCHAR(50),
    HireDate DATE,
    IsActive BIT DEFAULT 1
);

-- SalesQuotas - has SalesRepID but NO declared FK
CREATE TABLE sales.SalesQuotas (
    QuotaID INT IDENTITY(1,1) PRIMARY KEY,
    SalesRepID INT,  -- Should infer to SalesReps.SalesRepID
    QuotaYear INT,
    QuotaAmount DECIMAL(12,2)
);

-- =============================================================================
-- hr schema tables
-- =============================================================================

-- Employees table
CREATE TABLE hr.Employees (
    EmployeeID INT IDENTITY(1,1) PRIMARY KEY,
    EmployeeName NVARCHAR(100) NOT NULL,
    Email VARCHAR(100),
    DepartmentID INT,
    HireDate DATE,
    Salary DECIMAL(10,2)
);

-- Departments table
CREATE TABLE hr.Departments (
    DepartmentID INT IDENTITY(1,1) PRIMARY KEY,
    DepartmentName NVARCHAR(100) NOT NULL,
    ManagerID INT  -- Self-reference to Employees (for advanced inference test)
);

-- Add FK from Employees to Departments (declared)
ALTER TABLE hr.Employees
ADD CONSTRAINT FK_Employees_Departments
    FOREIGN KEY (DepartmentID) REFERENCES hr.Departments(DepartmentID);

-- =============================================================================
-- Create indexes for testing
-- =============================================================================

CREATE INDEX IX_Orders_CustomerID ON dbo.Orders(CustomerID);
CREATE INDEX IX_Orders_OrderDate ON dbo.Orders(OrderDate);
CREATE INDEX IX_Products_CategoryCode ON dbo.Products(CategoryCode);
CREATE INDEX IX_ShipmentLog_CustomerID ON dbo.ShipmentLog(CustomerID);

-- =============================================================================
-- Insert sample data
-- =============================================================================

-- Customers
INSERT INTO dbo.Customers (CustomerName, Email, Status) VALUES
('Acme Corp', 'contact@acme.com', 'Active'),
('Global Industries', 'info@global.com', 'Active'),
('Local Shop', 'owner@localshop.com', 'Inactive'),
('Big Enterprise', 'sales@bigent.com', 'Active'),
('Small Business', 'hello@smallbiz.com', 'Pending');

-- Categories
INSERT INTO dbo.Categories (CategoryCode, CategoryName) VALUES
('ELEC', 'Electronics'),
('FURN', 'Furniture'),
('FOOD', 'Food & Beverage'),
('CLTH', 'Clothing');

-- Products
INSERT INTO dbo.Products (ProductName, SKU, CategoryCode, UnitPrice) VALUES
('Laptop Pro', 'LP-001', 'ELEC', 999.99),
('Office Chair', 'OC-001', 'FURN', 249.99),
('Coffee Maker', 'CM-001', 'ELEC', 79.99),
('Desk Lamp', 'DL-001', 'FURN', 39.99),
('Notebook Set', 'NS-001', NULL, 12.99);

-- Orders
INSERT INTO dbo.Orders (CustomerID, OrderDate, Status, TotalAmount) VALUES
(1, '2026-01-01', 'Completed', 1249.98),
(2, '2026-01-05', 'Completed', 289.98),
(1, '2026-01-10', 'Pending', 79.99),
(3, '2026-01-12', 'Cancelled', 39.99),
(4, '2026-01-15', 'Pending', 999.99);

-- OrderItems
INSERT INTO dbo.OrderItems (OrderID, ProductID, Quantity, UnitPrice) VALUES
(1, 1, 1, 999.99),
(1, 2, 1, 249.99),
(2, 2, 1, 249.99),
(2, 4, 1, 39.99),
(3, 3, 1, 79.99),
(4, 4, 1, 39.99),
(5, 1, 1, 999.99);

-- Departments
INSERT INTO hr.Departments (DepartmentName) VALUES
('Engineering'),
('Sales'),
('Marketing'),
('Human Resources');

-- Employees
INSERT INTO hr.Employees (EmployeeName, Email, DepartmentID, Salary) VALUES
('John Smith', 'john@company.com', 1, 85000),
('Jane Doe', 'jane@company.com', 2, 75000),
('Bob Wilson', 'bob@company.com', 1, 95000),
('Alice Brown', 'alice@company.com', 3, 70000);

-- SalesReps
INSERT INTO sales.SalesReps (RepName, Region) VALUES
('Mike Johnson', 'East'),
('Sarah Davis', 'West'),
('Tom Garcia', 'Central');

-- SalesQuotas
INSERT INTO sales.SalesQuotas (SalesRepID, QuotaYear, QuotaAmount) VALUES
(1, 2026, 500000),
(2, 2026, 450000),
(3, 2026, 400000);

-- ShipmentLog (for inference testing)
INSERT INTO dbo.ShipmentLog (OrderNum, CustomerID, ShipDate, Carrier) VALUES
(1, 1, '2026-01-02', 'FedEx'),
(2, 2, '2026-01-06', 'UPS'),
(5, 4, '2026-01-16', 'USPS');

-- ProductReviews (for inference testing)
INSERT INTO dbo.ProductReviews (ProductID, CustomerID, Rating, ReviewText) VALUES
(1, 1, 5, 'Excellent laptop!'),
(2, 2, 4, 'Comfortable chair'),
(3, 1, 3, 'Works well');

PRINT 'Test database schema created successfully';
GO

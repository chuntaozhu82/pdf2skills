# Comment Density Research

## IBM Study Findings

**Optimal Ratio**: Approximately 1 comment per 10 statements

**Comprehensibility Curve:**
```
Clarity
    ^
    |        /--\
    |       /    \
    |      /      \
    |     /        \
    |____/          \____
       Low    Optimal   High
       Density
```

**Below optimal**: Code lacks explanatory context
**Above optimal**: Signal-to-noise ratio decreases, harder to find relevant information

## Practical Application

### Example of Optimal Density
```python
def calculate_interest(principal, rate, years):
    # Convert annual rate to monthly decimal (0.05 -> 0.00417)
    monthly_rate = rate / 12 / 100
    
    # Calculate total months for compound interest
    months = years * 12
    
    # Apply compound interest formula: P(1 + r)^n
    return principal * (1 + monthly_rate) ** months
```

3 comments for ~10 lines of code = appropriate density

### Example of Over-commenting
```python
def calculate_interest(principal, rate, years):
    # Declare principal variable
    principal = principal
    
    # Convert annual rate to monthly decimal
    # First divide by 12 to get monthly rate
    # Then divide by 100 to convert percentage to decimal
    # Example: 5% becomes 0.00417
    monthly_rate = rate / 12 / 100
    
    # Calculate months
    # Multiply years by 12
    months = years * 12
    
    # Return result
    # Using compound interest formula
    return principal * (1 + monthly_rate) ** months
```

Too many comments explaining obvious code

### Example of Under-commenting
```python
def calc(p, r, y):
    mr = r / 12 / 100
    m = y * 12
    return p * (1 + mr) ** m
```

No context about what calculations represent or why
# Emex API and Armtek Brand Filtering Fixes

## Issues Identified

### 1. Emex API Returning Empty Results
**Problem**: Emex API was returning empty results for all articles:
- `emex: D-127206 → []`
- `emex: 33369-37020 → []`
- `emex: 33369-37010 → []`

**Root Cause**: 
- API might be blocked or rate-limited
- Response format might have changed
- Insufficient error handling and debugging
- No fallback mechanism when API fails

### 2. Armtek Still Finding Garbage Brands
**Problem**: Armtek was finding garbage brands in logs but filtering them correctly:
- Finding: 'TelegramWhatsapp', 'Цена', 'NEW', 'Программа лояльности', etc.
- But correctly returning only: 'HINO', 'JMC', 'PRC' (whitelist brands)

**Root Cause**: 
- Whitelist was working but needed expansion for legitimate brands
- Some legitimate brands were being filtered out

## Solutions Implemented

### 1. Fixed Emex API Issues

#### A. Enhanced Error Handling and Debugging
```python
# Added detailed logging for API responses:
log_debug(f"Emex API: статус {response.status_code} для {artikul}")
log_debug(f"Emex API: структура ответа для {artikul}: {list(data.keys())}")
log_debug(f"Emex API: searchResult ключи: {list(search_result.keys())}")
log_debug(f"Emex API: найдено {len(makes_list)} makes для {artikul}")
```

#### B. Improved Headers and Timeout
```python
# Enhanced headers for better API compatibility:
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

# Increased timeout for stability:
timeout=20  # Increased from 15 to 20 seconds
```

#### C. Added HTTP Fallback Method
```python
# Fallback HTTP scraping when API fails:
fallback_url = f"https://emex.ru/products/{encoded_artikul}"
response = requests.get(fallback_url, headers=headers, timeout=15)

# Parse HTML for brands using multiple selectors:
brand_selectors = [
    '.brand-name', '.product-brand', '.manufacturer-name',
    '.vendor-title', '.item-brand', '.brand__name',
    '[data-brand]', '.make-name'
]
```

#### D. Better Response Structure Handling
```python
# More robust JSON parsing:
search_result = data.get("searchResult", {})
if search_result:
    makes = search_result.get("makes", {})
    if makes:
        makes_list = makes.get("list", [])
        for item in makes_list:
            if isinstance(item, dict) and "make" in item:
                brand = item["make"]
                if brand and brand.strip():
                    brands.add(brand.strip())
```

### 2. Improved Armtek Brand Filtering

#### A. Expanded Whitelist
```python
# Added more legitimate brands to whitelist:
allowed_brands = {
    'QUNZE', 'NIPPON', 'MOTORS MATTO', 'JMC', 'KOBELCO', 'PRC', 
    'HUANG LIN', 'ERISTIC', 'HINO', 'OOTOKO', 'MITSUBISHI', 'TOYOTA',
    'AUTOKAT', 'ZEVS', 'PITWORK', 'HITACHI', 'NISSAN', 'DETOOL', 'CHEMIPRO',
    'STELLOX', 'FURO', 'EDCON', 'REPARTS'
}
```

#### B. Case-Insensitive Matching
```python
# Improved case-insensitive matching:
brand_upper = brand_clean.upper()
if brand_upper in allowed_brands:
    for allowed_brand in allowed_brands:
        if allowed_brand.upper() == brand_upper:
            filtered.append(allowed_brand)
            break
```

## Expected Results

### 1. Emex API Improvements
- ✅ **Better Debugging**: Detailed logs show exactly what's happening with API calls
- ✅ **Fallback Mechanism**: HTTP scraping when API fails
- ✅ **Improved Headers**: Better compatibility with Emex API
- ✅ **Longer Timeouts**: More stable connections
- ✅ **Robust Parsing**: Better handling of different response formats

### 2. Armtek Filtering Improvements
- ✅ **Expanded Whitelist**: More legitimate brands included
- ✅ **Better Case Handling**: Proper case-insensitive matching
- ✅ **Clean Output**: Only approved brands in results
- ✅ **No Garbage**: UI elements and navigation terms filtered out

## Files Modified

1. **`backend/api/autopiter_parser.py`**:
   - Enhanced `get_brands_by_artikul_emex()` function with better error handling
   - Added HTTP fallback method for Emex
   - Expanded Armtek whitelist with more legitimate brands
   - Improved debugging and logging throughout

## Testing Recommendations

1. **Test Emex API**: Verify API calls are working and returning results
2. **Check Fallback**: Ensure HTTP scraping works when API fails
3. **Validate Armtek**: Confirm only approved brands appear in results
4. **Monitor Logs**: Check detailed debugging output for troubleshooting

## Log Analysis

From the logs, we can see:
- **Armtek filtering is working**: Finding garbage but returning only approved brands
- **Emex needs debugging**: Empty results need investigation with new detailed logs
- **Fallback mechanism**: Should provide alternative when API fails

The enhanced debugging will help identify exactly why Emex API is returning empty results and the fallback mechanism should provide results even if the API is blocked. 
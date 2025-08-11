# Emex API Compression Handling Fixes

## Issues Identified

### 1. Emex API Returning Compressed Data
**Problem**: Emex API was returning compressed (gzip/br) data even though content-type was `application/json`:
```
Emex API: content-type: application/json; charset=utf-8
Emex API: ошибка декодирования JSON для 1883107731: Expecting value: line 1 column 1 (char 0)
Emex API: ответ для 1883107731: 
޵JzDw%GY>B:ISZ_-ܠ洸,}   xY8NOKwA~_rzY[z-tjlqqfjrl...
```

**Root Cause**: 
- API was returning compressed data (gzip/br) but requests library wasn't properly handling it
- Content-type header was misleading - it said JSON but response was compressed
- No fallback mechanism for handling compression issues

### 2. Manual API Access Works
**Problem**: When accessing the API manually, it returns proper JSON:
```json
{
  "searchResult": {
    "num": "D-126177",
    "make": "Mitsubishi",
    "makes": {
      "list": [
        {
          "id": 384,
          "make": "Mitsubishi",
          "num": "MD126177"
        },
        {
          "id": 15550,
          "make": "Дизель",
          "num": "D126177"
        }
      ]
    }
  }
}
```

**Expected Brands**: `['Mitsubishi', 'Дизель']`

## Solutions Implemented

### 1. Multiple Request Attempts with Different Configurations

#### A. First Attempt - Normal Headers
```python
# Первая попытка с обычными заголовками
response = requests.get(
    api_url,
    headers=headers,
    timeout=20
)
```

#### B. Second Attempt - Disabled Compression
```python
# Вторая попытка с отключенным сжатием
headers_no_compression = headers.copy()
headers_no_compression['Accept-Encoding'] = 'identity'
response = requests.get(
    api_url,
    headers=headers_no_compression,
    timeout=20
)
```

### 2. Enhanced Response Handling

#### A. Better Content-Type and Encoding Logging
```python
log_debug(f"Emex API: content-type: {response.headers.get('content-type', 'unknown')}")
log_debug(f"Emex API: content-encoding: {response.headers.get('content-encoding', 'none')}")
```

#### B. Improved JSON Parsing
```python
# Обработка структуры ответа Emex
search_result = data.get("searchResult", {})
if search_result:
    # Проверяем makes - это основной источник брендов
    makes = search_result.get("makes", {})
    if makes:
        makes_list = makes.get("list", [])
        for item in makes_list:
            if isinstance(item, dict):
                # Извлекаем бренд из поля "make"
                brand = item.get("make")
                if brand and brand.strip():
                    brands.add(brand.strip())
```

#### C. Fallback JSON Parsing
```python
# Пробуем декодировать как текст и посмотреть что получилось
text_content = response.text
if text_content.startswith('{'):
    # Возможно это JSON, но с проблемами кодировки
    data = json.loads(text_content)
    # Process the data...
```

### 3. Enhanced HTTP Fallback Filtering

#### A. Additional Garbage Words
```python
# Added more Emex-specific garbage words:
'дилерская сеть', 'запчасти для то', 'каталог запчастей', 'оптового', 'покупателя'
```

#### B. Better Text Pattern Matching
```python
# Enhanced text extraction with stricter filtering for fallback
for tag in soup.find_all(['span', 'div', 'a', 'h3', 'h4', 'h5']):
    text = tag.get_text(strip=True)
    if text and len(text) > 2 and len(text) < 50:
        # Check for garbage words...
```

## Expected Results

### 1. API Response Handling
- ✅ **Multiple Attempts**: Two different request configurations
- ✅ **Compression Handling**: Proper handling of gzip/br responses
- ✅ **Better Debugging**: Detailed logging of content-type and encoding
- ✅ **Fallback Parsing**: Alternative JSON parsing methods

### 2. Brand Extraction
- ✅ **Correct Structure**: Proper parsing of `searchResult.makes.list[].make`
- ✅ **Multiple Brands**: Extraction of all brands from the makes list
- ✅ **Clean Output**: Only legitimate brand names like 'Mitsubishi', 'Дизель'

### 3. Error Recovery
- ✅ **Graceful Degradation**: Fallback to HTTP scraping if API fails
- ✅ **Better Logging**: Clear indication of what's happening at each step
- ✅ **No Crashes**: Proper exception handling throughout

## Files Modified

1. **`backend/api/autopiter_parser.py`**:
   - Enhanced `get_brands_by_artikul_emex()` with multiple request attempts
   - Added compression handling and better JSON parsing
   - Improved error recovery and debugging

## Testing Recommendations

1. **Test API Responses**: Verify both request configurations work
2. **Check Compression**: Ensure compressed responses are handled properly
3. **Validate Brand Extraction**: Confirm brands like 'Mitsubishi', 'Дизель' are extracted
4. **Monitor Logs**: Check detailed debugging output for troubleshooting

## Log Analysis

From the logs, we can see:
- **API Issue**: Content-type says JSON but response is compressed
- **Multiple Attempts**: Two different request configurations will be tried
- **Better Parsing**: Proper extraction from `makes.list[].make` structure
- **Fallback Ready**: HTTP scraping as backup if API fails

The enhanced compression handling should now properly extract brands like 'Mitsubishi' and 'Дизель' from the Emex API, even when the response is compressed. 
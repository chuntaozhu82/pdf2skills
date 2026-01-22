# Rate Limiting and Concurrency Analysis

## Current State: **NO RATE LIMITING IMPLEMENTED**

### Summary
The system currently has **ZERO rate limiting or concurrency controls** for API calls. All requests are made sequentially without delays, which leads to immediate rate limit violations.

---

## API Clients Analysis

### 1. GLM-4.7 Client (`sku_extractor.py`)
- **Location**: `GLM4Client.chat()`
- **Rate Limiting**: ❌ None
- **Delays**: ❌ None
- **Concurrency**: Sequential (one request at a time)
- **Timeout**: 120 seconds
- **Issue**: Makes immediate sequential requests → hits 429 errors immediately

```python
# Current implementation (lines 113-131)
def chat(self, messages: list, max_tokens: int = 8000, temperature: float = 0.3) -> str:
    response = requests.post(url, headers=headers, json=payload, timeout=120)
    # No delay, no retry, no rate limit handling
```

### 2. DeepSeek R1 Client (`semantic_density.py`)
- **Location**: `DeepSeekR1Client.score_chunk()`
- **Rate Limiting**: ❌ None
- **Delays**: ❌ None
- **Concurrency**: Sequential
- **Timeout**: 60 seconds
- **Issue**: Processes 15 samples sequentially → hits rate limits

```python
# Current implementation (lines 339-353)
for i, score in enumerate(samples):
    gold = self.llm.score_chunk(...)  # Immediate call, no delay
```

### 3. DeepSeek V3.2 Client (`onion_peeler.py`)
- **Location**: `DeepSeekClient.chat()`
- **Rate Limiting**: ❌ None
- **Delays**: ❌ None
- **Concurrency**: Sequential
- **Timeout**: None (uses requests default)
- **Issue**: Makes multiple LLM calls during chunking → potential rate limits

---

## Processing Loops Analysis

### SKU Extractor (`extract_all()`)
```python
# Lines 390-400
for i, chunk_info in enumerate(self.chunks_index):
    skus = self.extract_from_chunk(chunk_info)  # Immediate API call
    # No delay between chunks
```
- **Concurrency**: Sequential
- **Rate Control**: None
- **Result**: All 12 chunks processed immediately → 429 errors

### Semantic Density (`calibrate_weights()`)
```python
# Lines 504-515
for i, score in enumerate(samples):
    gold = self.llm.score_chunk(...)  # Immediate API call
    # No delay between samples
```
- **Concurrency**: Sequential
- **Rate Control**: None
- **Result**: 15 samples processed immediately → timeouts and 429 errors

---

## Observed API Limits

### GLM-4.7 (BigModel)
- **Observed Behavior**: 
  - First 1-2 requests succeed
  - Then immediate 429 "Too Many Requests"
  - Timeout errors on longer requests (120s)
- **Estimated Limit**: Very low (likely < 5 requests/minute)

### DeepSeek R1 (SiliconFlow)
- **Observed Behavior**:
  - Some requests succeed
  - Frequent timeouts (60s)
  - 429 errors after multiple requests
- **Estimated Limit**: Moderate (likely 10-20 requests/minute)

---

## Recommendations

### Immediate Fixes Needed

1. **Add Delays Between Requests**
   ```python
   import time
   time.sleep(2)  # 2 second delay between requests
   ```

2. **Implement Exponential Backoff**
   ```python
   import time
   def retry_with_backoff(func, max_retries=3):
       for attempt in range(max_retries):
           try:
               return func()
           except requests.exceptions.HTTPError as e:
               if e.response.status_code == 429:
                   wait = 2 ** attempt
                   time.sleep(wait)
               else:
                   raise
   ```

3. **Add Rate Limit Detection**
   ```python
   if response.status_code == 429:
       retry_after = response.headers.get('Retry-After', 60)
       time.sleep(int(retry_after))
   ```

4. **Implement Request Queue/Throttling**
   - Use a token bucket or leaky bucket algorithm
   - Limit to N requests per minute

### Configuration Options

Add to `.env`:
```env
# Rate Limiting
API_REQUEST_DELAY=2.0          # Seconds between requests
API_MAX_RETRIES=3              # Max retry attempts
API_RETRY_BACKOFF=2            # Exponential backoff multiplier
API_RATE_LIMIT_RPM=30          # Requests per minute limit
```

---

## Comparison with Other Modules

### skill_seekers Module
- ✅ Has `RateLimitHandler` class
- ✅ Implements retry logic
- ✅ Has timeout handling
- ✅ Supports multiple strategies (wait, switch, fail)

### pdf2skills Module
- ❌ No rate limiting
- ❌ No retry logic
- ❌ No delays
- ❌ No error recovery

---

## Impact Assessment

### Current Impact
- **SKU Extractor**: 0-2 SKUs extracted out of 12 chunks (0-17% success rate)
- **Semantic Density**: Partial success, frequent timeouts
- **Onion Peeler**: Generally works (fewer API calls)

### With Rate Limiting
- **Expected Success Rate**: 90%+ 
- **Processing Time**: 2-3x longer (due to delays)
- **Reliability**: Much higher

---

## Conclusion

**The system has NO rate limiting mechanisms**, which causes immediate API rate limit violations. Adding delays, retry logic, and rate limit detection is **critical** for reliable operation.

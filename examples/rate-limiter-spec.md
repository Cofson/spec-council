# Spec: API rate limiter

## Summary
Limit how many requests each API key can make, so one client cannot slow down the service for others.

## Requirements
- Each API key gets 100 requests per minute.
- When a key goes over the limit, the API returns an error.
- Limits reset every minute.

## Out of scope
- Billing for extra requests.

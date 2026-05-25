curl -s -X POST http://localhost:8000/admin/test-email \
  -H "Content-Type: application/json" \
  -H "X-Admin-Secret: abc@123@def!" \
  -d '{"email":"ntaluja2025@gmail.com"}'

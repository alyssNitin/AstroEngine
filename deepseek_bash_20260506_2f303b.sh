docker run -d --name narayan-pg \
  -e POSTGRES_USER=narayan \
  -e POSTGRES_PASSWORD=yourpassword \
  -e POSTGRES_DB=narayan_astro \
  -p 5432:5432 \
  postgres:16-alpine
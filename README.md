# SDN_APIserv_demo


Project structure:
```shell
.
├── Dockerfile
├── README.md
├── app.py
├── compose.yaml
├── test.py
└── requirements.txt
```


compose.yaml
```shell
services:
  redis:
    image: redislabs/redismod
    ports:
      - '6379:6379'
    networks:
      - flask-network
  web:
    build:
      context: .
      target: builder
    # flask requires SIGINT to stop gracefully
    # (default stop signal from Compose is SIGTERM)
    stop_signal: SIGINT
    ports:
      - '8000:8000'
    volumes:
      - .:/code
    depends_on:
      - redis
      - db
    environment:
      - MYSQL_HOST=db
      - MYSQL_USER=operator
      - MYSQL_PASSWORD=operator
      - MYSQL_DATABASE=security
    networks:
      - flask-network
  db:
    image: mysql:8.0
    container_name: flask-mysql
    command: --default-authentication-plugin=mysql_native_password
    environment:
      MYSQL_ROOT_PASSWORD: 1qaz@WSX3edc
      MYSQL_DATABASE: security
    ports:
      - "3316:3306"
    volumes:
      - mysql-data:/var/lib/mysql
      - ./security.sql:/docker-entrypoint-initdb.d/security.sql
    networks:
      - flask-network

volumes:
  mysql-data:  # MySQL data persistence

networks:
  flask-network:
    driver: bridge
```

## Deploy with docker compose
```shell
$ docker compose up -d
[+] Running 24/24
 ⠿ redis Pulled   
 ...
⠿ 565225d89260 Pull complete
[+] Building 12.7s (10/10) FINISHED
 => [internal] load build definition from Dockerfile...
[+] Running 5/5
 ⠿ Network flask-redis_flask-network  Creat...                                     0.1s
 ⠿ Volume "flask-redis_mysql-data"    Created                                      0.0s
 ⠿ Container flask-redis-redis-1      Started                                      1.0s
 ⠿ Container flask-mysql              Started                                      0.9s
 ⠿ Container flask-redis-web-1        Started                                      1.5s

Expected result
Listing containers must show one container running and the port mapping as below:
$ docker compose ps
NAME                  IMAGE                COMMAND                  SERVICE             CREATED              STATUS              PORTS
flask-mysql           mysql:8.0            "docker-entrypoint.s…"   db                  About a minute ago   Up About a minute   33060/tcp, 0.0.0.0:3316->3306/tcp, :::3316->3306/tcp
flask-redis-redis-1   redislabs/redismod   "redis-server --load…"   redis               About a minute ago   Up About a minute   0.0.0.0:6379->6379/tcp, :::6379->6379/tcp
flask-redis-web-1     flask-redis-web      "python3 app.py"         web                 About a minute ago   Up About a minute   0.0.0.0:8000->8000/tcp, :::8000->8000/tcp
```

## Test API
```
$ curl -X POST -H "Content-Type:application/json" http://<your IP>/flowentry/check -d '{"dpid":"0000000000010501","ip":"192.168.1.5/32"}'
{
  "check": "Success",
  "flow_num_db": 0,
  "flow_num_sw": 0
}
```



## Shutdown with docker compose
```shell
$ docker compose down

[+] Running 5/5
 ⠿ Container flask-redis-web-1        Removed                                          0.9s
 ⠿ Container flask-redis-redis-1      Removed                                          0.4s
 ⠿ Container flask-mysql              Removed                                          1.4s
 ⠿ Volume flask-redis_mysql-data      Removed                                          0.1s
 ⠿ Network flask-redis_flask-network  Removed                                          0.2s
```



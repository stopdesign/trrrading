# Trrrading

Yet Another Trading Platform


## Usage

Конфигурационные файлы лежат в `src/bot_config/`

#### Backtest
```
manage.py run broker_conf.yaml strategy_conf.yaml --backtest
```

#### Trading
```
manage.py run broker_conf.yaml strategy_conf.yaml
```

#### Отправка ордеров
Для синхронизации ордеров с IBKR (в обе стороны)
должен быть запущен сервис синхронизации:
```
manage.py sync_ibkr broker_conf.yaml
```

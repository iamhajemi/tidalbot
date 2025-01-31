#!/bin/bash

while true; do
    echo "GitHub'dan güncel kod alınıyor..."
    git pull origin main
    
    echo "Bot başlatılıyor..."
    python bot.py
    
    echo "Bot durdu, 5 saniye sonra yeniden başlatılacak..."
    sleep 5
done 
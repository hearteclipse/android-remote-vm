#!/bin/bash
# Script para configurar firewall do GCP e reiniciar serviços

echo "🔍 Verificando regras de firewall existentes..."
gcloud compute firewall-rules list --filter='name~webrtc OR name~udp' --format='table(name,allowed,sourceRanges)'

echo ""
echo "🔧 Criando/atualizando regra de firewall para WebRTC..."

# Deletar regra antiga se existir
gcloud compute firewall-rules delete allow-webrtc-udp --quiet 2>/dev/null || true

# Criar nova regra
gcloud compute firewall-rules create allow-webrtc-udp \
    --allow=udp:49152-49252 \
    --source-ranges=0.0.0.0/0 \
    --description="WebRTC UDP ports for android-remote-vm" \
    --network=default \
    --priority=1000

echo ""
echo "✅ Regra criada! Verificando..."
gcloud compute firewall-rules describe allow-webrtc-udp

echo ""
echo "🔄 Reiniciando backend para aplicar configurações..."
cd ~/android-remote-vm
docker-compose restart backend

echo ""
echo "⏳ Aguardando 5 segundos..."
sleep 5

echo ""
echo "📋 Logs do backend (últimas 30 linhas):"
docker logs vmi-backend --tail 30

echo ""
echo "✅ Pronto! Agora teste no navegador: http://34.42.79.210:8080/"


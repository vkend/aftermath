#!/bin/sh
# Make a local certificate authority and a server certificate for the phone page, with macOS's own openssl.
#
#   scripts/make_certs.sh [folder]        # default: data/certs (git-ignored, never committed)
#
# The iPhone trusts the CA once (AirDrop aftermath-ca.crt to it; the steps are in the README), and from then on the
# laptop's server certificate, which names the laptop's network address, its .local name and localhost. The CA is
# made once and reused, so when the laptop's address changes, run this again and only the server certificate is
# remade: the phone needs nothing new.
#
# The CA can only vouch for local addresses and .local names (X.509 name constraints), so even its own key couldn't
# be used to impersonate a public website to the phone. iOS accepts server certificates lasting at most 825 days;
# these last 820. Key identifiers are included because strict verifiers (Python 3.13's, for one) require them.
set -eu
out="${1:-data/certs}"
ip="$(ipconfig getifaddr en0 || ipconfig getifaddr en1)"
host="$(scutil --get LocalHostName).local"
mkdir -p "$out"
umask 077

if [ ! -f "$out/aftermath-ca.key" ]; then
  cat > "$out/ca.cnf" <<EOF
[req]
distinguished_name = dn
x509_extensions = ca
prompt = no
[dn]
CN = Aftermath local CA (this laptop only)
[ca]
basicConstraints = critical, CA:TRUE, pathlen:0
keyUsage = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always
nameConstraints = critical, permitted;IP:192.168.0.0/255.255.0.0, permitted;IP:10.0.0.0/255.0.0.0, permitted;IP:172.16.0.0/255.240.0.0, permitted;IP:127.0.0.0/255.0.0.0, permitted;DNS:local, permitted;DNS:localhost
EOF
  openssl genrsa -out "$out/aftermath-ca.key" 2048 2>/dev/null
  openssl req -x509 -new -sha256 -days 820 -key "$out/aftermath-ca.key" -config "$out/ca.cnf" \
    -out "$out/aftermath-ca.crt"
  echo "made the CA: $out/aftermath-ca.crt (AirDrop this one file to the iPhone)"
fi

cat > "$out/server.cnf" <<EOF
[req]
distinguished_name = dn
prompt = no
[dn]
CN = $host
[server]
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid, issuer
subjectAltName = IP:$ip, DNS:$host, DNS:localhost, IP:127.0.0.1
EOF
openssl genrsa -out "$out/server.key" 2048 2>/dev/null
openssl req -new -sha256 -key "$out/server.key" -config "$out/server.cnf" -out "$out/server.csr"
openssl x509 -req -sha256 -days 820 -in "$out/server.csr" -CA "$out/aftermath-ca.crt" -CAkey "$out/aftermath-ca.key" \
  -CAcreateserial -extfile "$out/server.cnf" -extensions server -out "$out/server.crt" 2>/dev/null
rm -f "$out/server.csr"
echo "made the server certificate for https://$ip:8443 and https://$host:8443"

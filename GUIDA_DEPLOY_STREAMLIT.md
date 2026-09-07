# Guida rapida - Pubblicazione gratuita su Streamlit Community Cloud

## Obiettivo

Pubblicare La Tartuca - Aggiornamento corsi su un indirizzo del tipo:

`https://latartuca-corsi.streamlit.app`

senza installare Python sui PC della responsabile.

## 1. Crea un repository GitHub privato

Nome consigliato: `la-tartuca-corsi`.

Carica nel repository **solo** i file di questa cartella online-ready. Non caricare PDF o Word reali dell'associazione.

## 2. Controlla la struttura

La root del repository deve contenere almeno:

```text
app.py
requirements.txt
src/
.streamlit/config.toml
```

## 3. Accedi a Streamlit Community Cloud

Apri `https://share.streamlit.io` e accedi con il tuo account.

Collega GitHub. Per utilizzare un repository privato, autorizza Streamlit ad accedere ai repository privati.

## 4. Crea l'app

- premi **Create app**;
- scegli il repository `la-tartuca-corsi`;
- branch: normalmente `main`;
- entrypoint: `app.py`;
- scegli un URL, per esempio `latartuca-corsi`;
- in **Advanced settings** scegli **Python 3.12**;
- premi **Deploy**.

Il primo deploy può richiedere qualche minuto.

## 5. Rendila privata

Dalle impostazioni dell'app, sezione **Sharing**, imposta:

**Only specific people can view this app**

Aggiungi l'indirizzo email della responsabile. Potrà accedere con Google oppure tramite link/codice monouso inviato via email, secondo il suo account.

## 6. Test consigliato

Da un secondo browser o PC:

1. apri l'URL dell'app;
2. verifica che venga richiesto l'accesso;
3. carica PDF e Word di test;
4. completa un caso dubbio;
5. scarica Word operativo e report;
6. premi **Nuova lavorazione / azzera sessione** e verifica che i dati spariscano dalla sessione.

## 7. Aggiornare l'app in futuro

Modifica i file nel repository GitHub e fai commit/push. Streamlit Community Cloud rileva le modifiche e aggiorna automaticamente l'app.

Se modifichi `requirements.txt`, il servizio ricrea anche l'ambiente Python.

## Note importanti

- L'app non salva intenzionalmente i documenti caricati in un archivio permanente.
- Ogni browser ha una sessione separata.
- Se l'app non viene usata per molte ore, Community Cloud può metterla in sospensione; al successivo accesso può essere necessario riattivarla.
- Streamlit Community Cloud consente una sola app privata per workspace/account alla volta.

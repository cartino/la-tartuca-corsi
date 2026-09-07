# La Tartuca - Aggiornamento corsi (online-ready v0.3)

App Streamlit per preparare il Word operativo destinato al webmaster.

## Flusso

**PDF trimestre attuale + Word di base → confronto → decisioni sui soli casi dubbi → Word operativo + report**

L'app non modifica direttamente il sito.

## File necessari al deploy

- `app.py`
- cartella `src/`
- `requirements.txt`
- `.streamlit/config.toml`

## Avvio locale facoltativo

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Privacy dei documenti

Il codice dell'app non salva PDF/Word caricati in database, repository GitHub o archivi permanenti. I file vengono elaborati nella sessione Streamlit corrente per generare i risultati da scaricare.

**Non aggiungere mai PDF o Word reali dell'associazione al repository GitHub.** Il `.gitignore` incluso blocca per precauzione i formati di documento più comuni.

## Multi-PC

La responsabile può aprire la stessa app da PC diversi. Ogni browser ha però una sessione separata: una lavorazione non completata non viene sincronizzata automaticamente tra dispositivi.

Per la pubblicazione gratuita su Streamlit Community Cloud, seguire `GUIDA_DEPLOY_STREAMLIT.md`.

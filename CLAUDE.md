# Cervello del progetto — Clone-code

Memoria persistente per Claude Code su questo repository: cosa contiene, come è
organizzato e quali skill sono disponibili.

## Contenuto del repository

| File / cartella | Descrizione |
|---|---|
| `email_briefing.py` | Generatore di briefing email. Legge la inbox Gmail via Gmail API, raggruppa i messaggi per priorità e salva una bozza HTML "Briefing Mattutino – <data>". Pensato per essere schedulato via cron (07:30 e 23:30). Richiede `credentials.json` OAuth2 e produce `token.json` al primo avvio. |
| `.claude/skills/` | Skill di progetto caricate automaticamente da Claude Code in questa directory. |

## Skill disponibili

### `consulente-previdenziale` → `.claude/skills/consulente-previdenziale/SKILL.md`

Consulente pensionistico INPS. Copre AGO, Gestione Separata, ex-INPDAP,
artigiani e commercianti. La skill guida sei fasi: raccolta dati contributivi,
determinazione del sistema di calcolo (retributivo / misto / contributivo puro),
analisi dei canali di uscita (vecchiaia, anticipata, Quota 103, Opzione Donna,
APE Sociale, Lavoratori Precoci, Isopensione), stima dell'assegno, strumenti di
ottimizzazione (riscatto laurea, totalizzazione, cumulo gratuito, ricongiunzione,
prosecuzione volontaria) e output finale strutturato.

Si attiva su richieste che riguardano pensione, contributi INPS, estratto conto,
riscatto laurea, Quota 103, APE Sociale, previdenza.

Vincoli da rispettare sempre quando la skill è attiva:

- La FASE 1 (raccolta dati) è obbligatoria prima di qualsiasi analisi, salvo che
  i dati siano già stati forniti dall'utente.
- L'analisi è indicativa, non è consulenza legale certificata: rimandare sempre
  al Patronato (INCA, ACLI, CAF) o a un consulente del lavoro abilitato, e alla
  simulazione ufficiale "La Mia Pensione" su myINPS.
- Le misure straordinarie (Quota 103, APE Sociale, Opzione Donna) sono soggette a
  proroga annuale: verificarne la validità per l'anno corrente prima di
  presentarle come disponibili.
- I coefficienti di trasformazione e gli importi soglia riportati nella skill
  sono riferiti al 2025 (Circ. INPS 62/2024): aggiornarli quando cambiano.

## Convenzioni

- Le nuove skill vanno in `.claude/skills/<nome-skill>/SKILL.md`, con frontmatter
  YAML `name` + `description` (la description deve includere i trigger, perché è
  ciò che determina l'attivazione della skill).
- Ogni nuova skill va registrata in questo file, nella sezione "Skill disponibili".
- Lingua di lavoro del repository: italiano.

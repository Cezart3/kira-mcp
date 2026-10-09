# kira-mcp — ghid în română

**Spune-i AI-ului tău ce chirie cauți, oriunde în România. El caută live pe
storia.ro, publi24.ro și lajumate.ro și îți răspunde cu anunțurile potrivite.**

![kira-mcp în Claude Code](docs/demo.svg)

Exemple de cereri:

- *„Caută-mi o garsonieră în Sibiu sub 350 €, cu centrală proprie.”*
- *„Apartament cu 2 camere în Cluj, maxim 20 de minute pe jos de UMF, cu loc de parcare.”*
- *„Ce chirii sunt în Șelimbăr de la proprietar, fără agenție?”*
- *„Parcarea e inclusă la anunțul ăsta? <link>”*
- *„Loc de parcare de închiriat în Brașov sub 60 €.”*

Ce face în plus față de filtrele site-urilor:

- caută pe **3 site-uri deodată** și elimină dublurile (același apartament
  postat pe două site-uri apare o singură dată);
- funcționează pentru **orice localitate** — 3.181 municipii, orașe și comune,
  nu doar orașele mari; înțelege și fără diacritice (`targu mures`, `tg mures`,
  `cluj`, `buc`);
- citește textul anunțului: **centrală proprie sau termoficare**, **parcare
  inclusă / în zonă / deloc**, proprietar sau agenție, stradă, etaj;
- calculează **câte minute faci pe jos** până la un loc ales de tine;
- scoate anunțurile care nu sunt chirii: vânzări, doar loc de parcare, regim hotelier;
- nu returnează telefoane sau e-mailuri — contactezi proprietarul pe site.

---

## Instalare pas cu pas

### Pasul 1 — instalează `uv` (o singură dată)

`uv` descarcă și pornește automat kira-mcp. Nu trebuie să instalezi Python.

**Windows** — deschide PowerShell și rulează:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**macOS / Linux** — în Terminal:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Închide terminalul, deschide unul nou și verifică:

```bash
uvx --version
```

Dacă vezi un număr de versiune, e gata.

### Pasul 2 — conectează-l la AI-ul tău

#### Claude Code

```bash
claude mcp add kira -s user -- uvx kira-rentals-mcp
```

Verifică: `claude mcp list` → trebuie să apară `kira: ... ✓ Connected`.

#### Claude Desktop

1. Deschide Claude Desktop → **Settings** → **Developer** → **Edit Config**.
   Se deschide fișierul `claude_desktop_config.json`.
2. Pune în el (dacă are deja ceva, adaugă doar blocul `"kira"` în `"mcpServers"`):

   ```json
   {
     "mcpServers": {
       "kira": {
         "command": "uvx",
         "args": ["kira-rentals-mcp"]
       }
     }
   }
   ```

3. Salvează, apoi **închide complet** Claude Desktop (iconița de lângă ceas →
   Quit) și pornește-l din nou.
4. În meniul de unelte/conectori trebuie să apară **kira**.

Dacă apare o eroare că serverul nu pornește: rulează `where uvx` (Windows) sau
`which uvx` (macOS) și pune calea completă la `"command"`. Pe Windows dublezi
backslash-urile: `"C:\\Users\\nume\\.local\\bin\\uvx.exe"`.

#### Cursor, Windsurf, Gemini CLI

Același JSON ca la Claude Desktop, în `~/.cursor/mcp.json`,
`~/.codeium/windsurf/mcp_config.json`, respectiv `~/.gemini/settings.json`.

#### VS Code (Copilot, modul agent)

Fișier `.vscode/mcp.json` în proiect:

```json
{
  "servers": {
    "kira": {
      "type": "stdio",
      "command": "uvx",
      "args": ["kira-rentals-mcp"]
    }
  }
}
```

#### Codex CLI

În `~/.codex/config.toml`:

```toml
[mcp_servers.kira]
command = "uvx"
args = ["kira-rentals-mcp"]
```

### Pasul 3 — întreabă

Scrie-i AI-ului ce cauți, în română sau engleză. Prima căutare durează câteva
secunde în plus (se descarcă pachetul); următoarele durează 2–20 de secunde.

---

## Fără AI: din terminal

```bash
uvx --from kira-rentals-mcp kira search "Cluj-Napoca" --rooms 2 --max-price 500
uvx --from kira-rentals-mcp kira search Iasi --heating centrala_proprie --near "Palas Mall" --sort distance
uvx --from kira-rentals-mcp kira listing https://www.storia.ro/ro/oferta/...
uvx --from kira-rentals-mcp kira parking Brasov --max-price 80
uvx --from kira-rentals-mcp kira find Floresti
```

| Opțiune | Ce înseamnă |
|---|---|
| `--county` | Județul, când numele e ambiguu (există 6 Florești). Sau direct `"Floresti, Prahova"`. |
| `--min-price`, `--max-price` | Chiria lunară în **euro** (anunțurile în lei sunt convertite la ~5 lei/€). |
| `--rooms 1 2` | 1 = garsonieră; 4 = 4 sau mai multe. |
| `--heating` | `centrala_proprie` (centrală proprie) sau `termoficare` (termoficare sau centrală de bloc). |
| `--parking` | `included`, `likely_included`, `area_possible` (în zonă / contra cost), `none`, `unknown`. |
| `--owner-only` | Doar proprietari (fără comision), unde site-ul precizează. |
| `--keywords` | Cuvinte care trebuie să apară toate în anunț (`"balcon mobilat"`). |
| `--near`, `--max-walk` | Loc de referință și maxim minute pe jos. |
| `--sort` | `newest`, `price_asc`, `price_desc`, `distance`. |
| `--json` | Rezultat în JSON. |

## Limite — ce trebuie să știi

- **OLX și imobiliare.ro nu sunt incluse**: blochează accesul automat (HTTP 403),
  iar kira-mcp nu încearcă să ocolească blocarea. Pentru acoperire completă,
  verifică și acolo.
- Încălzirea și parcarea sunt deduse din textul anunțului. Când anunțul nu
  spune, rezultatul e `unknown` — nu ghicim.
- Distanțele sunt estimări (linie dreaptă × 1,3, mers 4,7 km/h). Se folosește
  locația declarată în anunț; cele cu doar cartierul au precizie `district`
  (aproximativă), iar cele fără nicio adresă apar la final, fără distanță.
- E făcut pentru căutarea personală de chirie, nu pentru colectare în masă:
  se identifică, face pauze între cereri și ține paginile în cache 10 minute.

Licență: MIT. Documentația completă (engleză): [README.md](README.md).

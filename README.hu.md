# SCARLINE

*[English version: README.md](README.md)*

Gyors és nehéz, 2D-s oldalnézetes rakétás játék Pygame-mel. A rakéta magától halad előre, te csak a hajtóművet irányítod. Minden hiba után a szektor elölről indul és a kráterek eltűnnek, de az összes korábbi próbálkozásod **szellemként** együtt indul veled, és a hibapontján felrobbantja a pályát, így ott át lehet menni.

![Képernyőkép](./Assets/Screenshots/screenshot.png "Képernyőkép")

## Letöltés (Windows)

Töltsd le a `Scarline-win64.zip` fájlt a [Releases](https://github.com/dedsecds22/Scarline/releases) oldalról, csomagold ki, és indítsd a `Scarline.exe`-t. Pythonra nincs szükség. A mentés (`save.json`) az exe mellé kerül.

## Futtatás forrásból

Python 3.10+ és Pygame 2.x szükséges.

```powershell
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python main.py
```

## Windows release készítése

```powershell
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\python.exe -m PyInstaller --noconfirm --onedir --windowed --name Scarline --add-data "Assets\Background;Assets\Background" --add-data "Assets\Fonts;Assets\Fonts" --add-data "Assets\Ground_Stone;Assets\Ground_Stone" --add-data "Assets\Other;Assets\Other" main.py
```

## Irányítás

| Billentyű | Funkció |
|---|---|
| `Space` / `W` / `Fel` | Hajtómű |
| `Esc` | Menü (a menüben: vissza) |
| `R` | A szektor teljes újrakezdése (szellemek és rekord törlődnek) |
| `Fel` / `Le` (`W` / `S`) | Menüválasztás |
| `Bal` / `Jobb` (`A` / `D`) | Szektor váltása a menüben |
| `Enter` / `Space` | Megerősítés; a szektor végén a következő szektor |

## Játékmenet

- Fix seed alapján determinisztikusan generált pálya hosszú, meredek emelkedőkkel és szűk járattal; minden szektor szűkebb és gyorsabb az előzőnél.
- **Szellemek:** minden hiba után a korábbi próbák újra végigmennek, és a hibapontjukon krátert robbantanak. Minden újabb szellem kicsit korábban indul, így a robbanások előbb érkeznek, mint te, nem egyszerre.
- **Kapuk:** hirtelen, szinte teljesen zárt szakaszok, amelyeken addig nem lehet átjutni, amíg egy szellem ki nem robbantja őket.
- **Gravitációváltás** (2. szektortól 1, a 4.-től 2 zóna): az egész nézet fejjel lefelé fordul, a gravitáció felfelé húz, a hajtómű lefelé tol. Lila (belépés) és kék (kilépés) sáv jelzi.
- **Gravitációs elforgatás** (6. szektortól 1, a 8.-tól 2 zóna): az egész nézet 90 fokkal elfordul; felfelé haladsz, a gravitáció jobbra húz, a hajtómű balra tol. Narancs (belépés) és zöld (kilépés) sáv jelzi.
- **10. szektor:** minden kombinálva, többek között egy fordított gravitációs zóna, amely egy elforgatott zóna közepén kezdődik.
- **11–16. szektor:** szélesebb járat, de **mozgó aknák** pásztázzák a járatot. A szellemek az aknákat is elpusztítják, ahogy a krátert is kirobbantják: ahol egy korábbi próba lezuhant, ott a következő körben az akna eltűnik.
- **13. szektortól:** **sötét zónák** — a pálya fekete, csak rendszeres villámlás (kb. másodpercenként) világítja meg; az aknákon piros jelzőfény látszik. Ibolya (belépés) és sárga (kilépés) sáv jelzi.
- **15–16. szektor:** minden kombinálva: fordítós és elforgatós zónák, sötét zónák és mozgó aknák.
- Szektorválasztó (1–16) a főmenüben, szektoronként külön rekorddal.
- HUD távolsággal, sebességgel, gravitációjelzővel, figyelmeztetésekkel és zónajelölőkkel a haladási csíkon.

## Technikai megjegyzések

- Fix 120 Hz-es fizikai lépés, így a szellemek felvétele mindig szinkronban játszódik vissza.
- A grafika az `Assets` mappából töltődik ([assets.py](assets.py)): parallax űrháttér, animált nap, bolygók, ismétlődő terepcsempe, rakéta-sprite, PNG-s robbanás és por, egyedi betűtípus.
- JSON mentés az aktuális szektorral és a szektoronkénti rekordokkal (a szellemek nem mentődnek).
- A kráterek a mintavételezett padló- és plafongörbékbe vágódnak, nem tetszőleges poligonba, ami egyszerűbb és jól tesztelhető.

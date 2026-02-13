# GGM OpenRegister

OpenRegister configuration files generated from the [Gemeentelijk Gegevensmodel (GGM)](https://github.com/Gemeente-Delft/Gemeentelijk-Gegevensmodel) v2.5.0.

## What is this?

This repository contains auto-generated [OpenRegister](https://github.com/ConductionNL/openregister) configuration files (`.openregister.json`) for all GGM domains. Each domain becomes a separate register with all its entity schemas.

OpenRegister can import these configurations directly from GitHub using its built-in configuration import system.

## Domains

| File | Domain | Schemas |
|------|--------|---------|
| `0-bestuur-politiek.openregister.json` | Bestuur, Politiek en Ondersteuning | 13 |
| `1-veiligheid-vergunningen.openregister.json` | Veiligheid en Vergunningen | 30 |
| `2-verkeer-vervoer-waterstaat.openregister.json` | Verkeer, Vervoer en Waterstaat | 20 |
| `3-economie.openregister.json` | Economie | 6 |
| `4-onderwijs.openregister.json` | Onderwijs | 27 |
| `5-sport-cultuur-recreatie.openregister.json` | Sport, Cultuur en Recreatie | 84 |
| `6-sociaal-domein.openregister.json` | Sociaal Domein | 287 |
| `7-volksgezondheid-milieu.openregister.json` | Volksgezondheid en Milieu | 16 |
| `8-volkshuisvesting-leefomgeving.openregister.json` | Volkshuisvesting, Leefomgeving en Stedelijke Vernieuwing | 120 |
| `9-interne-organisatie.openregister.json` | Interne Organisatie | 148 |
| `10-dienstverlening.openregister.json` | Dienstverlening | 16 |
| `99-kern.openregister.json` | Kern (Core) | 188 |

**Total: 955 schemas across 12 registers**

## Cross-domain References

Schemas reference entities in other domains via `$ref` and `objectConfiguration` with the target register slug. For example, a schema in the Sociaal Domein that references a Kern entity:

```json
{
  "heeftAlsEigenaar": {
    "type": "object",
    "$ref": "rechtspersoon",
    "objectConfiguration": {
      "register": "ggm-kern",
      "schema": "rechtspersoon"
    }
  }
}
```

## Importing into OpenRegister

These files are automatically discoverable by OpenRegister's GitHub configuration search (files matching `*.openregister.json` with `x-openregister` metadata).

To import a domain manually, use the OpenRegister configuration import with the GitHub URL of the desired `.openregister.json` file.

## Regenerating

To regenerate the configuration files from a newer GGM version:

1. Clone the GGM repository or download the `.qea` file
2. Run the generator:

```bash
python3 generate.py /path/to/Gemeentelijk\ Gegevensmodel.qea
```

The generator parses the Enterprise Architect QEA file (which is SQLite) using Python's built-in `sqlite3` module. No external dependencies are required.

## Source

- GGM Repository: https://github.com/Gemeente-Delft/Gemeentelijk-Gegevensmodel
- GGM Website: https://www.gemeentelijkgegevensmodel.nl/
- GGM Version: 2.5.0

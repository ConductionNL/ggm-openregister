#!/usr/bin/env python3
"""
GGM to OpenRegister Configuration Generator

Reads the Gemeentelijk Gegevensmodel (GGM) from its Enterprise Architect
QEA file (SQLite) and generates OpenRegister-compatible configuration files
in the *.openregister.json format.

Each GGM domain becomes a separate register with all its schemas (entities).
Cross-domain references are handled via schema slug + register slug references.

Usage:
    python3 generate.py [path-to-qea-file]

If no path is given, defaults to looking for the QEA in a 'ggm-source' directory.
"""

import json
import os
import re
import sqlite3
import sys
from collections import defaultdict


# ─── Configuration ───────────────────────────────────────────────────────────

GGM_VERSION = "2.5.0"
GGM_ROOT_PACKAGE_ID = 3  # "Delfts Gemeentelijk Gegevensmodel" under root
GITHUB_REPO = "ConductionNL/ggm-openregister"
GITHUB_BRANCH = "main"
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# Top-level domain packages (direct children of root package ID=3)
DOMAIN_PACKAGES = {
    4: {
        "name": "0 Bestuur, Politiek en Ondersteuning",
        "slug": "ggm-bestuur-politiek",
        "file": "0-bestuur-politiek.openregister.json",
    },
    12: {
        "name": "1 Veiligheid en Vergunningen",
        "slug": "ggm-veiligheid-vergunningen",
        "file": "1-veiligheid-vergunningen.openregister.json",
    },
    15: {
        "name": "2 Verkeer, Vervoer en Waterstaat",
        "slug": "ggm-verkeer-vervoer-waterstaat",
        "file": "2-verkeer-vervoer-waterstaat.openregister.json",
    },
    22: {
        "name": "3 Economie",
        "slug": "ggm-economie",
        "file": "3-economie.openregister.json",
    },
    25: {
        "name": "4 Onderwijs",
        "slug": "ggm-onderwijs",
        "file": "4-onderwijs.openregister.json",
    },
    32: {
        "name": "5 Sport, Cultuur en Recreatie",
        "slug": "ggm-sport-cultuur-recreatie",
        "file": "5-sport-cultuur-recreatie.openregister.json",
    },
    52: {
        "name": "6 Sociaal Domein",
        "slug": "ggm-sociaal-domein",
        "file": "6-sociaal-domein.openregister.json",
    },
    91: {
        "name": "7 Volksgezondheid en Milieu",
        "slug": "ggm-volksgezondheid-milieu",
        "file": "7-volksgezondheid-milieu.openregister.json",
    },
    95: {
        "name": "8 Volkshuisvesting, Leefomgeving en Stedelijke Vernieuwing",
        "slug": "ggm-volkshuisvesting-leefomgeving",
        "file": "8-volkshuisvesting-leefomgeving.openregister.json",
    },
    114: {
        "name": "9 Interne Organisatie",
        "slug": "ggm-interne-organisatie",
        "file": "9-interne-organisatie.openregister.json",
    },
    135: {
        "name": "10 Dienstverlening",
        "slug": "ggm-dienstverlening",
        "file": "10-dienstverlening.openregister.json",
    },
    367: {
        "name": "99 Kern",
        "slug": "ggm-kern",
        "file": "99-kern.openregister.json",
    },
}


# ─── Type Mapping ────────────────────────────────────────────────────────────

def map_type(type_name, length=0):
    """Map a GGM/EA attribute type to a JSON Schema type definition."""
    if not type_name:
        return {"type": "string"}

    t = type_name.strip()
    t_lower = t.lower()

    # Boolean types
    if t_lower in ("boolean", "bool", "indic", "stdindijn"):
        return {"type": "boolean"}

    # Integer types
    if t_lower in ("int", "integer", "number"):
        return {"type": "integer"}
    # Nxx patterns (e.g. N1, N4, N6, N8, N11)
    if re.match(r'^N\d+$', t):
        return {"type": "integer"}

    # Number/decimal types
    if t_lower in ("double", "decimal", "float"):
        return {"type": "number"}
    if t_lower == "bedrag" or t_lower == "geldbedrag":
        return {"type": "number"}
    # Nxx,x patterns (e.g. N10.2, N18,2, N3,1)
    if re.match(r'^N\d+[.,]\d+$', t):
        return {"type": "number"}

    # Date/time types
    if t_lower in ("date", "datum"):
        return {"type": "string", "format": "date"}
    if t_lower in ("datetime", "datumtijd"):
        return {"type": "string", "format": "date-time"}
    if t_lower == "time":
        return {"type": "string", "format": "time"}
    if t_lower in ("jaar", "year"):
        return {"type": "string", "format": "date"}
    if t_lower == "onvolledgedatum":
        return {"type": "string"}

    # URI/URL/email
    if t_lower in ("url", "uri"):
        return {"type": "string", "format": "uri"}
    if t_lower == "email":
        return {"type": "string", "format": "email"}
    if t_lower == "iban":
        return {"type": "string"}
    if t_lower == "telefoonnummer":
        return {"type": "string"}

    # Geometry types
    if t_lower in ("point", "punt", "gm_point", "gm_punt"):
        return {"type": "string", "format": "geo"}
    if t_lower in ("gm_surface", "gm_multisurface", "vlak", "spatial",
                    "gm_curve", "gm_lijn", "gm_multicurve", "gm_multipoint",
                    "multipuntlijn(multi)vlak"):
        return {"type": "string", "format": "geo"}

    # GUID
    if t_lower == "guid":
        return {"type": "string", "format": "uuid"}

    # Binary
    if t_lower == "blob":
        return {"type": "string", "format": "binary"}
    if t_lower == "image":
        return {"type": "string", "format": "binary"}

    # ANxx patterns (alphanumeric with max length)
    an_match = re.match(r'^AN(\d+)$', t)
    if an_match:
        return {"type": "string", "maxLength": int(an_match.group(1))}

    # VARCHAR types
    if t_lower.startswith("varchar"):
        len_match = re.match(r'varchar2?\((\d+)\)', t_lower)
        if len_match:
            return {"type": "string", "maxLength": int(len_match.group(1))}
        return {"type": "string", "maxLength": 255}

    # Char/string types
    if t_lower in ("char", "characterstring", "string", "text", "tekst", "tan"):
        return {"type": "string"}

    # Single-letter or short codes that are string enums in EA
    if len(t) <= 3 and t.isalpha():
        return {"type": "string"}

    # Enumeration reference or complex type — will be resolved later
    # For now, return string as fallback
    return {"type": "string"}


def slugify(name):
    """Convert a GGM entity name to a URL-friendly slug."""
    s = name.lower()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'[\s]+', '-', s)
    s = re.sub(r'-+', '-', s)
    s = s.strip('-')
    return s


def camel_to_slug(name):
    """Convert CamelCase to a slug."""
    s = re.sub(r'([A-Z])', r'-\1', name).strip('-')
    return slugify(s)


# ─── Database Access ─────────────────────────────────────────────────────────

class GGMDatabase:
    """Reads GGM data from the Enterprise Architect QEA (SQLite) file."""

    def __init__(self, qea_path):
        self.conn = sqlite3.connect(qea_path)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()

        # Build lookup caches
        self._build_package_tree()
        self._build_object_cache()
        self._build_enum_cache()

    def _build_package_tree(self):
        """Build a parent→children map for packages."""
        self.cursor.execute("SELECT Package_ID, Name, Parent_ID FROM t_package")
        self.packages = {}
        self.package_children = defaultdict(list)
        for row in self.cursor.fetchall():
            self.packages[row["Package_ID"]] = dict(row)
            self.package_children[row["Parent_ID"]].append(row["Package_ID"])

    def _build_object_cache(self):
        """Cache all objects by ID for quick lookup."""
        self.cursor.execute(
            "SELECT Object_ID, Name, Object_Type, Package_ID, Stereotype, Note, ea_guid "
            "FROM t_object"
        )
        self.objects = {}
        for row in self.cursor.fetchall():
            self.objects[row["Object_ID"]] = dict(row)

    def _build_enum_cache(self):
        """Cache enumeration literals."""
        self.enums = {}
        self.cursor.execute(
            "SELECT Object_ID FROM t_object WHERE Object_Type = 'Enumeration'"
        )
        enum_ids = [row["Object_ID"] for row in self.cursor.fetchall()]
        for eid in enum_ids:
            self.cursor.execute(
                "SELECT Name FROM t_attribute WHERE Object_ID = ? ORDER BY Pos",
                (eid,),
            )
            self.enums[eid] = [row["Name"] for row in self.cursor.fetchall()]

    def get_descendant_packages(self, parent_id):
        """Recursively get all descendant package IDs."""
        result = [parent_id]
        for child_id in self.package_children.get(parent_id, []):
            result.extend(self.get_descendant_packages(child_id))
        return result

    def get_classes_in_packages(self, package_ids):
        """Get all Class objects with Stereotype='Objecttype' in the given packages."""
        placeholders = ",".join("?" * len(package_ids))
        self.cursor.execute(
            f"SELECT Object_ID, Name, Note, Stereotype, Package_ID, ea_guid "
            f"FROM t_object "
            f"WHERE Object_Type = 'Class' AND Stereotype = 'Objecttype' "
            f"AND Package_ID IN ({placeholders})",
            package_ids,
        )
        return [dict(row) for row in self.cursor.fetchall()]

    def get_enumerations_in_packages(self, package_ids):
        """Get all Enumeration objects in the given packages."""
        placeholders = ",".join("?" * len(package_ids))
        self.cursor.execute(
            f"SELECT Object_ID, Name, Note, Package_ID "
            f"FROM t_object "
            f"WHERE Object_Type = 'Enumeration' "
            f"AND Package_ID IN ({placeholders})",
            package_ids,
        )
        return [dict(row) for row in self.cursor.fetchall()]

    def get_attributes(self, object_id):
        """Get all attributes for a given object."""
        self.cursor.execute(
            "SELECT Name, Type, Classifier, LowerBound, UpperBound, Notes, "
            "Length, \"Default\", Pos "
            "FROM t_attribute WHERE Object_ID = ? ORDER BY Pos",
            (object_id,),
        )
        return [dict(row) for row in self.cursor.fetchall()]

    def get_associations_for_object(self, object_id):
        """Get all Association/Aggregation connectors where this object is source or dest."""
        self.cursor.execute(
            "SELECT Connector_ID, Name, Connector_Type, "
            "Start_Object_ID, End_Object_ID, "
            "SourceCard, DestCard, SourceRole, DestRole "
            "FROM t_connector "
            "WHERE Connector_Type IN ('Association', 'Aggregation') "
            "AND (Start_Object_ID = ? OR End_Object_ID = ?)",
            (object_id, object_id),
        )
        return [dict(row) for row in self.cursor.fetchall()]

    def get_generalizations_for_object(self, object_id):
        """Get generalization connectors where this object is the child (Start)."""
        self.cursor.execute(
            "SELECT End_Object_ID "
            "FROM t_connector "
            "WHERE Connector_Type = 'Generalization' "
            "AND Start_Object_ID = ?",
            (object_id,),
        )
        return [row["End_Object_ID"] for row in self.cursor.fetchall()]

    def close(self):
        self.conn.close()


# ─── Generator ───────────────────────────────────────────────────────────────

class OpenRegisterGenerator:
    """Generates OpenRegister configuration files from GGM data."""

    def __init__(self, db):
        self.db = db

        # Build a global map: object_id → (domain_slug, schema_slug)
        # so we can resolve cross-domain references
        self.object_domain_map = {}  # object_id → domain package_id
        self.object_slug_map = {}    # object_id → schema slug
        self.domain_slug_map = {}    # domain package_id → register slug

        for pkg_id, info in DOMAIN_PACKAGES.items():
            self.domain_slug_map[pkg_id] = info["slug"]
            descendant_ids = db.get_descendant_packages(pkg_id)
            classes = db.get_classes_in_packages(descendant_ids)
            for cls in classes:
                obj_id = cls["Object_ID"]
                schema_slug = slugify(cls["Name"])
                self.object_domain_map[obj_id] = pkg_id
                self.object_slug_map[obj_id] = schema_slug

    def generate_all(self):
        """Generate all domain configuration files."""
        for pkg_id, info in DOMAIN_PACKAGES.items():
            print(f"Generating {info['file']}...")
            config = self._generate_domain(pkg_id, info)
            output_path = os.path.join(OUTPUT_DIR, info["file"])
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            schema_count = len(config["components"]["schemas"])
            print(f"  → {schema_count} schemas")

    def _generate_domain(self, pkg_id, domain_info):
        """Generate a single domain's OpenRegister configuration."""
        descendant_ids = self.db.get_descendant_packages(pkg_id)
        classes = self.db.get_classes_in_packages(descendant_ids)
        enumerations = self.db.get_enumerations_in_packages(descendant_ids)

        # Build local enum lookup (enum object_id → list of literal names)
        local_enums = {}
        for enum in enumerations:
            local_enums[enum["Object_ID"]] = self.db.enums.get(enum["Object_ID"], [])

        # Generate schemas
        schemas = {}
        schema_slugs = []
        for cls in classes:
            schema = self._generate_schema(cls, local_enums)
            if schema:
                slug = schema["slug"]
                # Handle duplicate slugs by appending a suffix
                original_slug = slug
                counter = 2
                while slug in schemas:
                    slug = f"{original_slug}-{counter}"
                    schema["slug"] = slug
                    counter += 1
                schemas[slug] = schema
                schema_slugs.append(slug)

        # Build register
        register = {
            "slug": domain_info["slug"],
            "title": f"GGM - {domain_info['name']}",
            "version": GGM_VERSION,
            "description": f"Gemeentelijk Gegevensmodel domain: {domain_info['name']}",
            "schemas": schema_slugs,
            "source": "internal",
        }

        # Build OpenAPI envelope
        config = {
            "openapi": "3.0.0",
            "info": {
                "title": f"GGM - {domain_info['name']}",
                "description": f"OpenRegister configuration for the Gemeentelijk Gegevensmodel (GGM) domain: {domain_info['name']}. "
                               f"Auto-generated from GGM v{GGM_VERSION}.",
                "version": GGM_VERSION,
            },
            "x-openregister": {
                "type": "application",
                "sourceType": "github",
                "sourceUrl": f"https://github.com/{GITHUB_REPO}",
                "openregister": "^v0.2.10",
                "github": {
                    "repo": GITHUB_REPO,
                    "branch": GITHUB_BRANCH,
                    "path": domain_info["file"],
                },
                "description": f"Gemeentelijk Gegevensmodel - {domain_info['name']}",
            },
            "components": {
                "schemas": schemas,
                "registers": {
                    domain_info["slug"]: register,
                },
            },
        }

        return config

    def _generate_schema(self, cls, local_enums):
        """Generate an OpenRegister schema from a GGM class."""
        obj_id = cls["Object_ID"]
        name = cls["Name"]
        slug = slugify(name)
        note = cls.get("Note") or ""

        # Clean up HTML from notes
        note = re.sub(r'<[^>]+>', '', note).strip()

        # Get attributes
        attributes = self.db.get_attributes(obj_id)
        properties = {}
        required = []

        for attr in attributes:
            prop = self._map_attribute(attr, local_enums)
            if prop:
                prop_name = self._sanitize_property_name(attr["Name"])
                properties[prop_name] = prop

                # Check if required (LowerBound >= 1)
                lower = attr.get("LowerBound", "0")
                if lower and str(lower) not in ("0", ""):
                    required.append(prop_name)

        # Get associations (relationships)
        associations = self.db.get_associations_for_object(obj_id)
        for assoc in associations:
            rel_prop = self._map_association(assoc, obj_id)
            if rel_prop:
                prop_name, prop_def = rel_prop
                if prop_name not in properties:
                    properties[prop_name] = prop_def

        # Build schema
        schema = {
            "slug": slug,
            "title": name,
            "version": GGM_VERSION,
            "description": note if note else f"GGM entity: {name}",
            "required": required if required else [],
            "properties": properties,
            "searchable": True,
            "hardValidation": False,
        }

        # Handle generalizations (inheritance)
        # Note: allOf is not used because OpenRegister's extractSchemaDelta()
        # tries to load parent schemas from the database during createFromArray(),
        # which fails if the parent hasn't been imported yet. Instead, we record
        # the inheritance as a description annotation.
        parent_ids = self.db.get_generalizations_for_object(obj_id)
        if parent_ids:
            parent_names = []
            for parent_id in parent_ids:
                if parent_id in self.object_slug_map:
                    parent_names.append(self.object_slug_map[parent_id])
            if parent_names:
                extends_note = f" Extends: {', '.join(parent_names)}."
                schema["description"] = schema["description"] + extends_note

        return schema

    def _map_attribute(self, attr, local_enums):
        """Map a GGM attribute to a JSON Schema property."""
        attr_name = attr["Name"]
        attr_type = attr.get("Type", "")
        classifier = attr.get("Classifier")
        notes = attr.get("Notes") or ""
        notes = re.sub(r'<[^>]+>', '', notes).strip()
        default_val = attr.get("Default")

        # Check if this attribute references an enumeration
        if classifier and str(classifier) not in ("0", ""):
            classifier_id = int(classifier)

            # Check if it's an enumeration
            if classifier_id in self.db.enums:
                literals = self.db.enums[classifier_id]
                prop = {"type": "string", "title": attr_name}
                if notes:
                    prop["description"] = notes
                if literals:
                    prop["enum"] = literals
                return prop

            # Check if it's a DataType (treat as string with the type name)
            obj = self.db.objects.get(classifier_id)
            if obj and obj["Object_Type"] == "DataType":
                prop = map_type(attr_type)
                prop["title"] = attr_name
                if notes:
                    prop["description"] = notes
                return prop

        # Standard type mapping
        prop = map_type(attr_type)
        prop["title"] = attr_name
        if notes:
            prop["description"] = notes
        if default_val and str(default_val).strip():
            prop["default"] = str(default_val).strip()

        return prop

    def _map_association(self, assoc, source_obj_id):
        """Map a GGM association to an OpenRegister relationship property."""
        start_id = assoc["Start_Object_ID"]
        end_id = assoc["End_Object_ID"]
        assoc_name = assoc.get("Name") or ""

        # Determine which end is the "other" object
        if start_id == source_obj_id:
            target_id = end_id
            cardinality = assoc.get("DestCard", "0..1")
            role = assoc.get("DestRole") or assoc_name
        else:
            target_id = start_id
            cardinality = assoc.get("SourceCard", "0..1")
            role = assoc.get("SourceRole") or assoc_name

        # Skip if target is not a known class
        if target_id not in self.object_slug_map:
            return None

        target_slug = self.object_slug_map[target_id]
        target_domain_id = self.object_domain_map.get(target_id)
        target_register = self.domain_slug_map.get(target_domain_id, "")

        # Build property name from role or association name
        prop_name = self._sanitize_property_name(role or target_slug)
        if not prop_name:
            prop_name = target_slug

        # Determine if it's a to-many or to-one relationship
        is_multiple = cardinality and ("*" in str(cardinality) or
                                        ".." in str(cardinality) and
                                        not str(cardinality).endswith("..1"))

        # Check cardinality more carefully
        if cardinality:
            card_str = str(cardinality)
            if card_str in ("0..*", "1..*", "*"):
                is_multiple = True
            elif card_str in ("0..1", "1", "1..1"):
                is_multiple = False

        # Note: We use $ref with bare slugs only. objectConfiguration is NOT
        # included because OpenRegister's importSchema() calls schemaMapper->find()
        # on objectConfiguration.schema, which throws ValidationException (not
        # DoesNotExistException) when the schema doesn't exist yet with
        # multitenancy/RBAC enabled, crashing the entire import.
        # The $ref slugs are safely left as strings when not resolvable.
        if is_multiple:
            prop = {
                "type": "array",
                "title": prop_name,
                "items": {
                    "type": "object",
                    "$ref": target_slug,
                },
            }
        else:
            prop = {
                "type": "object",
                "title": prop_name,
                "$ref": target_slug,
            }

        return (prop_name, prop)

    def _sanitize_property_name(self, name):
        """Sanitize a property name for use in JSON Schema."""
        if not name:
            return ""
        # Convert to camelCase-friendly format
        name = name.strip()
        # Remove special characters but keep alphanumeric and spaces
        name = re.sub(r'[^a-zA-Z0-9\s_]', '', name)
        # Convert spaces to camelCase
        parts = name.split()
        if not parts:
            return ""
        result = parts[0][:1].lower() + parts[0][1:]
        for part in parts[1:]:
            result += part[:1].upper() + part[1:]
        return result


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    # Find QEA file
    if len(sys.argv) > 1:
        qea_path = sys.argv[1]
    else:
        # Default paths to try
        candidates = [
            "/tmp/ggm-source/v2.5.0/Gemeentelijk Gegevensmodel.qea",
            os.path.join(OUTPUT_DIR, "ggm-source", "v2.5.0", "Gemeentelijk Gegevensmodel.qea"),
        ]
        qea_path = None
        for candidate in candidates:
            if os.path.exists(candidate):
                qea_path = candidate
                break

        if not qea_path:
            print("Error: Could not find GGM QEA file.")
            print("Usage: python3 generate.py [path-to-qea-file]")
            sys.exit(1)

    print(f"Reading GGM from: {qea_path}")
    print(f"Output directory: {OUTPUT_DIR}")
    print()

    db = GGMDatabase(qea_path)
    generator = OpenRegisterGenerator(db)
    generator.generate_all()
    db.close()

    print()
    print("Done! Generated configuration files:")
    for info in DOMAIN_PACKAGES.values():
        filepath = os.path.join(OUTPUT_DIR, info["file"])
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            print(f"  {info['file']} ({size:,} bytes)")


if __name__ == "__main__":
    main()

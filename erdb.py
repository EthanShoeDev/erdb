import argparse
import pathlib
import json
import scripts.config as cfg
from enum import Enum
from typing import Dict, List
from jsonschema import validate, RefResolver, ValidationError
from scripts.erdb_common import GeneratorDataBase, patch_keys, update_nested
from scripts.find_valid_values import find_valid_values
from scripts.game_version import GameVersion
from scripts.generate_armaments import ArmamentGeneratorData
from scripts.generate_armor import ArmorGeneratorData
from scripts.generate_ashes_of_war import AshOfWarGeneratorData
from scripts.generate_correction_graph import CorrectionGraphGeneratorData
from scripts.generate_reinforcements import ReinforcementGeneratorData
from scripts.generate_spirit_ashes import SpiritAshGeneratorData
from scripts.generate_talismans import TalismanGeneratorData

class Generator(Enum):
    ALL = "all"
    ARMAMENTS = "armaments"
    ARMOR = "armor"
    ASHES_OF_WAR = "ashes-of-war"
    CORRECTION_GRAPH = "correction-graph"
    REINFORCEMENTS = "reinforcements"
    SPIRIT_ASHES = "spirit-ashes"
    TALISMANS = "talismans"

    def __str__(self):
        return self.value

cfg.ROOT = pathlib.Path(__file__).parent.resolve()
cfg.VERSIONS = sorted([GameVersion.from_string(p.name) for p in (cfg.ROOT / "gamedata" / "_Extracted").glob("*") if GameVersion.match_path(p)], reverse=True)

_GENERATORS: Dict[Generator, GeneratorDataBase] = {
    Generator.ARMAMENTS: ArmamentGeneratorData,
    Generator.ARMOR: ArmorGeneratorData,
    Generator.ASHES_OF_WAR: AshOfWarGeneratorData,
    Generator.CORRECTION_GRAPH: CorrectionGraphGeneratorData,
    Generator.REINFORCEMENTS: ReinforcementGeneratorData,
    Generator.SPIRIT_ASHES: SpiritAshGeneratorData,
    Generator.TALISMANS: TalismanGeneratorData,
}

def get_args():
    parser = argparse.ArgumentParser(description="Interface for ERDB operations.")
    parser.add_argument("--generate", "-g", type=Generator, default=[], choices=list(Generator), nargs="+", help="The type of items to generate.")
    parser.add_argument("--find-values", "-f", type=str, help="Find all possible values of a field per param name, format: ParamName:FieldName.")
    parser.add_argument("--find-values-limit", type=int, default=-1, help="Limit find-values examples to X per value.")
    parser.add_argument("--gamedata-version", "-s", type=GameVersion.from_string, default=cfg.VERSIONS[0], choices=cfg.VERSIONS, help="Game version to source the data from.")
    return parser.parse_args()

def get_generators(args) -> List[Generator]:
    generators = set(args.generate)

    if Generator.ALL in generators:
        generators.update(Generator)
        generators.remove(Generator.ALL)

    return list(generators)

def generate(gendata: GeneratorDataBase, version: GameVersion) -> None:
    output_file = cfg.ROOT / str(version) / gendata.output_file()
    print(f"Output file: {output_file}", flush=True)

    if output_file.exists():
        with open(output_file, mode="r") as f:
            item_data_full = json.load(f)
        print(f"Loaded output file", flush=True)
    else:
        item_data_full = {gendata.element_name(): {}}
        print(f"Output file does not exist and will be created", flush=True)
    
    item_data_full["$schema"] = f"../schema/{gendata.schema_file()}"
    item_data = item_data_full[gendata.element_name()]
    print(f"Collected existing data with {len(item_data)} elements", flush=True)

    for row in gendata.main_param_iterator(gendata.main_param):
        key_name = gendata.get_key_name(row)

        new_obj = gendata.construct_object(row)
        cur_obj = item_data.get(key_name, {})

        update_nested(cur_obj, new_obj)
        cur_obj = patch_keys(cur_obj, gendata.schema_properties) if gendata.require_patching() else cur_obj

        item_data[key_name] = cur_obj

    print(f"Generated {len(item_data)} elements", flush=True)

    item_data_full[gendata.element_name()] = item_data
    ok = validate_and_write(output_file, gendata.schema_file(), item_data_full, gendata.schema_store)
    assert ok, "Generated schema failed to validate"

    print(f"Validated {len(item_data)} elements", flush=True)

def validate_and_write(file_path: str, schema_name: str, data: Dict, store: Dict[str, Dict]) -> bool:
    try:
        resolver = RefResolver(base_uri="unused", referrer="unused", store=store)
        validate(data, store[schema_name], resolver=resolver)

    except ValidationError as e:
        readable_path = "/".join(str(part) for part in e.path)
        print(f"Failed to validate \"{readable_path}\": {e.message}", flush=True)
        return False

    finally:
        with open(file_path, mode="w") as f:
            json.dump(data, f, indent=4)

    return True

def main():
    args = get_args()

    with open("latest_version.txt", mode="w") as f:
        f.write(str(cfg.VERSIONS[0]))

    (cfg.ROOT / str(args.gamedata_version)).mkdir(exist_ok=True)

    for gen in get_generators(args):
        print(f"\n>>> Generating \"{gen}\" from version {args.gamedata_version}", flush=True)
        gendata = _GENERATORS[gen].construct(args.gamedata_version)
        generate(gendata, args.gamedata_version)

    if args.find_values:
        parts = args.find_values.split(":")
        assert len(parts) == 2, "Incorrect find-values format"
        find_valid_values(parts[0], args.gamedata_version, parts[1], args.find_values_limit)

if __name__ == "__main__":
    main()
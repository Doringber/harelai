"""Validated workflow definitions: configuration never executes code."""
import json
import re
from importlib.resources import files
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PLACEHOLDER = re.compile(r'\{([a-z_][a-z0-9_.]*)\}')


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Labels(StrictModel):
    en: str = Field(min_length=1)
    he: str = Field(min_length=1)

    def get(self, language):
        return getattr(self, language)


class FieldSpec(StrictModel):
    type: Literal['text', 'number', 'flag', 'text_list']
    definition: str = Field(min_length=1, max_length=2000)
    label: Labels
    format: Literal['date', 'percent'] | None = None
    quote_terms: list[str] = Field(default_factory=list)


class RoleSpec(StrictModel):
    label: Labels
    fields: list[str] = Field(min_length=1)
    required: bool = True
    required_fields: list[str] = Field(default_factory=list)


class IdentitySpec(StrictModel):
    field: str
    required: bool = False
    normalize: Literal['text', 'name', 'date'] = 'text'


class Condition(StrictModel):
    field: str
    roles: list[str] = Field(min_length=1)
    op: Literal['eq', 'gte', 'lte', 'contains'] = 'eq'
    value: str | float | bool


class Rule(StrictModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9_]*$')
    label: Labels
    conditions: list[Condition] = Field(min_length=1)


class OutputField(StrictModel):
    field: str
    roles: list[str] = Field(min_length=1)
    select: Literal['unique', 'first'] = 'unique'
    display: Literal['name'] | None = None


class Profile(StrictModel):
    name: str = Field(pattern=r'^[a-z][a-z0-9_]*$')
    version: str = Field(min_length=1)
    fields: dict[str, FieldSpec]
    roles: dict[str, RoleSpec]
    identity: list[IdentitySpec] = Field(default_factory=list)
    blockers: list[Condition] = Field(default_factory=list)
    rules: list[Rule] = Field(min_length=1)
    output_fields: dict[str, OutputField] = Field(default_factory=dict)
    approval_reason: Labels | None = None

    @model_validator(mode='after')
    def references(self):
        if self.approval_reason:
            for text in (self.approval_reason.en, self.approval_reason.he):
                unknown = set(PLACEHOLDER.findall(text)) - self.output_fields.keys()
                if unknown:
                    raise ValueError(f'Approval reason uses unmapped output fields: {sorted(unknown)}')
        if any(not term.strip() for field in self.fields.values() for term in field.quote_terms):
            raise ValueError('Quote terms must be nonempty strings')
        if any(field.format == 'date' and field.type != 'text' for field in self.fields.values()):
            raise ValueError('Date fields must have text type')
        if any(field.format == 'percent' and field.type != 'number' for field in self.fields.values()):
            raise ValueError('Percent fields must have number type')
        reserved = {'schema_version', 'workflow', 'language', 'recommendation', 'rules', 'issues', 'facts', 'evidence', 'documents', 'model'}
        for path in self.output_fields:
            if path.split('.')[0] in reserved:
                raise ValueError('Output mappings cannot overwrite reserved result fields')
            if not all(part.isidentifier() for part in path.split('.')):
                raise ValueError('Output mappings must use dotted identifier paths')
            if any(other.startswith(path + '.') for other in self.output_fields):
                raise ValueError('Output mappings cannot overlap')
            selector = self.output_fields[path]
            if selector.display == 'name' and selector.field in self.fields and self.fields[selector.field].type != 'text':
                raise ValueError('Name display requires a text field')
        if not self.roles:
            raise ValueError('A profile must define document roles')
        for name, role in self.roles.items():
            if len(role.fields) != len(set(role.fields)):
                raise ValueError(f'Duplicate fields in role {name}')
            if set(role.fields) - self.fields.keys() or set(role.required_fields) - set(role.fields):
                raise ValueError(f'Unknown fields in role {name}')
        if len({r.id for r in self.rules}) != len(self.rules):
            raise ValueError('Duplicate rule IDs')
        for identity in self.identity:
            if identity.field not in self.fields:
                raise ValueError(f'Unknown identity field: {identity.field}')
            if identity.normalize in ('name', 'date') and self.fields[identity.field].type != 'text':
                raise ValueError('Name/date identity normalization requires text')
            if identity.required and any(identity.field not in r.fields for r in self.roles.values()):
                raise ValueError('Required identity field must be extracted from every role')
        conditions = [c for r in self.rules for c in r.conditions] + self.blockers
        for item in conditions + list(self.output_fields.values()):
            if item.field not in self.fields or set(item.roles) - self.roles.keys():
                raise ValueError(f'Unknown field or role: {item.field}')
            if any(item.field not in self.roles[role].fields for role in item.roles):
                raise ValueError(f'Field {item.field} is not extracted from a referenced role')
        for condition in conditions:
            field_type = self.fields[condition.field].type
            if condition.op in ('gte', 'lte') and (field_type != 'number' or type(condition.value) not in (int, float)):
                raise ValueError('Numeric comparisons require a number field and threshold')
            if condition.op == 'eq' and field_type == 'flag' and type(condition.value) is not bool:
                raise ValueError('Flag equality requires true or false')
            if condition.op == 'eq' and field_type == 'number' and type(condition.value) not in (int, float):
                raise ValueError('Number equality requires a numeric value')
            if condition.op == 'contains' and (field_type not in ('text', 'text_list') or not isinstance(condition.value, str)):
                raise ValueError('Contains requires a text/list field and string value')
        return self


def load_profile(reference='lung_biopsy', base_dir=None):
    """Built-in name or JSON path; case-provided paths resolve beside the case."""
    path = Path(reference)
    if path.suffix.lower() == '.json':
        if not path.is_absolute() and base_dir is not None:
            path = Path(base_dir) / path
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f'Cannot load profile {path}: {exc}') from exc
    else:
        if reference not in ('lung_biopsy', 'invoice_payment'):
            raise ValueError(f'Unknown workflow profile: {reference}')
        data = json.loads(files(__package__).joinpath(f'{reference}.json').read_text(encoding='utf-8'))
    return Profile.model_validate(data)

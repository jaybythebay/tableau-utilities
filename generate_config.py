import argparse
import json
import os
import shutil
from pprint import pprint

from tableau_utilities.tableau_file.tableau_file import Datasource
from tableau_utilities.tableau_server.tableau_server import TableauServer


def do_args():
    """ Parse arguments.

    Returns: an argparse.Namespace
    """

    parser = argparse.ArgumentParser(description='List columns in Tableau datasources')
    parser.add_argument(
        '--server',
        required=True,
        help='Tableau Server URL. i.e. <server_address> in https://<server_address>.online.tableau.com',
        default=None
    )
    parser.add_argument(
        '--site',
        required=True,
        help='Site name. i.e. <site> in https://<server_address>.online.tableau.com/#/site/<site>',
        default=None)
    parser.add_argument('--api_version', help='Tableau API version', default='2.8')
    parser.add_argument('--user', help='user name')
    parser.add_argument('--password', help='password')
    parser.add_argument('--token_secret', help='Personal Access Token Secret')
    parser.add_argument('--token_name', help='Personal Access Token Name')
    parser.add_argument('--datasource', help='The name of the datasources to generate a config for')
    return parser.parse_args()


def download_datasource(server, datasource_name=None, list_datasources=False):
    """ Downloads the specified datasources


    Args:
        server (TableauServer): A Tableau server object
        datasource_name: The name of the datasource to download
        list_datasources: Prints a sorted list of all the datasources from a site

    Returns:
        datasource: The datasource object for the datasource that was downloaded
        datasource_path: The path of the datasource that was downloaded
    """
    datasource_list = [d for d in server.get_datasources()]

    sources = []
    for datasource in datasource_list:
        if datasource.name == datasource_name:
            datasource_path = server.download_datasource(datasource.id, include_extract=False)
            return datasource, datasource_path


def choose_persona(role, role_type, datatype):
    """  The config relies on a persona which is a combination of role, role_type and datatype for each column.
    This returns the persona name or raises an exception if the combination is not found

    Args:
        role: dimension or measure
        role_type: nominal, ordinal, or quantitative
        datatype: string, date, datetype, real, or boolean

    """

    personas = [
        {"string_dimension": {
            "role": "dimension",
            "role_type": "nominal",
            "datatype": "string"
        }},
        {"date_dimension": {
            "role": "dimension",
            "role_type": "ordinal",
            "datatype": "date"
        }},
        {"datetime_dimension": {
            "role": "dimension",
            "role_type": "ordinal",
            "datatype": "datetime"
        }},
        {"date_measure": {
            "role": "measure",
            "role_type": "ordinal",
            "datatype": "date"
        }},
        {"datetime_measure": {
            "role": "measure",
            "role_type": "ordinal",
            "datatype": "datetime"
        }},
        {"discrete_number_dimension": {
            "role": "dimension",
            "role_type": "ordinal",
            "datatype": "integer"
        }},
        {"continuous_number_dimension": {
            "role": "dimension",
            "role_type": "quantitative",
            "datatype": "integer"
        }},
        {"discrete_number_measure": {
            "role": "measure",
            "role_type": "ordinal",
            "datatype": "integer"
        }},
        {"continuous_number_measure": {
            "role": "measure",
            "role_type": "quantitative",
            "datatype": "integer"
        }},
        {"discrete_decimal_dimension": {
            "role": "dimension",
            "role_type": "ordinal",
            "datatype": "real"
        }},
        {"continuous_decimal_dimension": {
            "role": "dimension",
            "role_type": "quantitative",
            "datatype": "real"
        }},
        {"discrete_decimal_measure": {
            "role": "measure",
            "role_type": "ordinal",
            "datatype": "real"
        }},
        {"continuous_decimal_measure": {
            "role": "measure",
            "role_type": "quantitative",
            "datatype": "real"
        }},
        {"boolean_dimension": {
            "role": "dimension",
            "role_type": "nominal",
            "datatype": "boolean"
        }}
    ]

    persona_name = None
    for persona in personas:
        for k, v in persona.items():
            if role == v['role'] and role_type == v['role_type'] == role_type and datatype == v['datatype']:
                persona_name = k
                break

    if persona_name is not None:
        return persona_name
    else:
        raise ValueError(
            f"There is no persona for the combination of ROLE {role}, ROLE_TYPE {role_type}, and DATATYPE {datatype}'")


def create_column_config(columns, datasource_name, folder_mapping):
    """ Generates a list of column configs with None for a folder

    Args:
        columns
        datasource_name
        folder_mapping: A list of dictionaries mapping column name to folder name

    ```{
      "Salesforce Opportunity Id": {
        "description": "The 18 digit account Id for a Salesforce opportunity",
        "folder": Name,
        "persona": "string_dimension",
        "datasources": [
          {
            "name": "Opportunity",
            "local-name": "SALESFORCE_OPPORTUNITY_ID",
            "sql_alias": "SALESFORCE_OPPORTUNITY_ID"
          }
        ]
      }
      ````

    Returns:
        column_configs: A dictionary with the configs for fields that are pulled from the source database
        calculated_column_configs: A dictionary with the configs for calculated fields added in the workbook that built
            the datasource

    """

    column_configs = {}
    calculated_column_configs = {}

    for c in columns:
        column_name = c['@name'][1:-1]

        # Skip the table datatype for now
        if c['@datatype'] == 'table':
            pass
        else:
            persona = choose_persona(role=c['@role'], role_type=c['@type'], datatype=c['@datatype'])

            description = ''
            if 'desc' in c:
                description = c['desc']['formatted-text']['run']

            folder_name = None
            if column_name in folder_mapping.keys():
                folder_name = folder_mapping[column_name]

            # Calculations are written to a separate config in the Airflow DAG
            if 'calculation' in c:

                calculated_column_configs[c['@caption']] = {
                    "description": description,
                    "calculation": c['calculation']['@formula'],
                    "folder": folder_name,
                    "persona": persona,
                    "datasources": [
                        {
                            "name": datasource_name,
                            "local-name": column_name,
                            "sql_alias": column_name
                        },
                    ]
                }

            else:

                column_configs[c['@caption']] = {
                    "description": description,
                    "folder": folder_name,
                    "persona": persona,
                    "datasources": [
                        {
                            "name": datasource_name,
                            "local-name": column_name,
                            "sql_alias": column_name
                        },
                    ]
                }

    return column_configs, calculated_column_configs


def build_folder_mapping(datasource_path):
    """  Builds a dictionary mapping columns to folders

    Args:
      The path to the datasource

    Returns:
        A dictionary with the mapping like

        ```
        {'column1': 'folderA',
         'column2': 'folderA',
         'column3': 'folderB',
        ```

    """

    folders = [c.dict() for c in Datasource(datasource_path).folders_common]

    mappings = {}
    for f in folders:
        folder_name = f['@name']

        for item in f['folder-item']:
            field_name = item['@name'][1:-1]
            mappings[field_name] = folder_name

    return mappings


def build_config(datasource, datasource_path):
    """ Builds a column config and caluclated field column config.  Writes each to individual files

    Args:
        datasource: The datasoruce object
        datasource_path: The name of the datasource

    """

    rows = dict()
    columns = [c.dict() for c in Datasource(datasource_path).columns]
    rows.setdefault(datasource.name, [])
    rows[datasource.name].extend(columns)

    # Build the folder mapping
    folder_mapping = build_folder_mapping(datasource_path)

    column_configs, calculated_column_configs = create_column_config(columns=columns,
                                                                     datasource_name=datasource.name,
                                                                     folder_mapping=folder_mapping)

    print('-' * 20, 'COLUMN CONFIG', '-' * 20)
    for config in column_configs:
        pprint(config, sort_dicts=False, width=200)

    print('-'*20, 'CALCULATED FIELD COLUMN CONFIG', '-'*20)
    for config in calculated_column_configs:
        pprint(config, sort_dicts=False, width=200)

    with open("column_config.json", "w") as outfile:
        json.dump(column_configs, outfile)

    with open("tableau_calc_config.json", "w") as outfile:
        json.dump(calculated_column_configs, outfile)

    print('DATSOURCE PATH:', datasource_path)
    print('COLUMN CONFIG PATH:', datasource_path)
    print('CALCULATED COLUMN CONFIG PATH:', datasource_path)


def generate_config(server, datasource_name):

    shutil.rmtree('tmp_tdsx', ignore_errors=True)
    tmp_folder = 'tmp_tdsx'
    os.makedirs(tmp_folder, exist_ok=True)
    os.chdir(tmp_folder)

    datasource, datasource_path = download_datasource(server, datasource_name)
    build_config(datasource, datasource_path)


if __name__ == '__main__':
    args = do_args()

    host = f'https://{args.server}.online.tableau.com'

    ts = TableauServer(
        personal_access_token_name=args.token_name,
        personal_access_token_secret=args.token_secret,
        user=args.user,
        password=args.password,
        site=args.site,
        host=host,
        api_version=args.api_version
    )

    generate_config(ts, datasource_name=args.datasource)

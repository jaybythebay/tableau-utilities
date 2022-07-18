import xml.etree.ElementTree as ET
import os

import xmltodict
from zipfile import ZipFile

import tableau_utilities.tableau_file.tableau_file_objects as tfo
from tableau_utilities.general.funcs import transform_tableau_object


class TableauFileError(Exception):
    """ A minimum viable exception. """

    def __init__(self, message):
        self.message = message


class TableauFile:
    """ The base class for a Tableau file, i.e. Datasource or Workbook. """

    def __init__(self, file_path):
        """
        Args:
            file_path (str): Path to a Tableau file

        """
        self.file_path = os.path.abspath(file_path)
        self.extension = file_path.split('.')[-1]
        self.file_path_without_extension = file_path.split('.')[0]
        self.file_name = self.file_path_without_extension.split('/')[-1]
        ''' Set on init '''
        self._tree: ET.ElementTree
        self._root: ET.Element
        self.__extract_xml()

    def __extract_xml(self, path=None):
        """ Extracts the XML from a Tableau file.

        Args:
            path (str): The path to the zipped Tableau file

        Returns: The contents of the Tableau File
        """
        if not path:
            path = self.file_path

        if self.extension in ['tdsx', 'twbx']:
            with ZipFile(path) as zip_file:
                for z in zip_file.filelist:
                    if z.filename.split('.')[-1] not in ['tds', 'twb']:
                        continue
                    self._tree = ET.parse(zip_file.open(z.filename))
                    self._root = self._tree.getroot()
        else:
            self._tree = ET.parse(path)
            self._root = self._tree.getroot()

    def unzip(self, unzip_all=False, extract_to=None):
        """ Unzips the Tableau File.

        Args:
            unzip_all (bool): True to unzip all zipped files
            extract_to: Override the source file directory and save the file to another location

        Returns: The path to the unzipped Tableau File
        """

        if extract_to is not None:
            file_dir = extract_to
        else:
            file_dir = os.path.dirname(self.file_path)

        tableau_file_path = None
        with ZipFile(self.file_path) as zip_file:
            for z in zip_file.filelist:
                ext = z.filename.split('.')[-1]
                if unzip_all:
                    zip_file.extract(member=z, path=file_dir)
                    if ext in ['tds', 'twb']:
                        tableau_file_path = os.path.join(file_dir, z.filename)
                elif not unzip_all and ext in ['tds', 'twb']:
                    zip_file.extract(member=z, path=file_dir)
                    tableau_file_path = os.path.join(file_dir, z.filename)
        return tableau_file_path

    def save(self):
        """ Save/Update the Tableau file with the XML changes made """

        if self.extension in ['tdsx', 'twbx']:
            with ZipFile(self.file_path, 'r') as zr, ZipFile(self.file_path, 'w') as zw:
                for file in zr.filelist:
                    if file.filename.split('.')[-1] in ['tds', 'twb']:
                        self._tree.write(zw.open(file.filename, 'w'))
        else:
            # Update the Tableau file's contents
            self._tree.write(self.file_path)


class Datasource(TableauFile):
    """
        A class representation of a Tableau Datasource.
        Used to update a Tableau Datasource by interacting with various elements,
        such as Columns, Folders, Connections, Metadata, etc.
    """

    def __init__(self, file_path):
        """
        Args:
            file_path (str): Path to a Tableau Datasource file; tds or tdsx
        """
        super().__init__(file_path)
        # Validate the file on initialization
        if self.extension not in ['tds', 'tdsx']:
            raise TableauFileError('File must be TDS or TDSX')

        self.connection: tfo.ParentConnection = self.__get_section(tfo.ParentConnection)
        self.aliases: tfo.Aliases = self.__get_section(tfo.Aliases)
        self.columns: tfo.TableauFileObjects[tfo.Column] = self.__get_section(tfo.Column, enforce_list=True)
        self.column_instance: tfo.ColumnInstance = self.__get_section(tfo.ColumnInstance)
        self.drill_paths: tfo.DrillPaths = self.__get_section(tfo.DrillPaths)
        self.folders_common: tfo.FoldersCommon = self.__get_section(tfo.FoldersCommon)
        self.date_options: tfo.DateOptions = self.__get_section(tfo.DateOptions)
        self.extract: tfo.Extract = self.__get_section(tfo.Extract)

    def sections(self):
        """ Yields each section defined in the class, for iteration """
        yield self.connection
        yield self.aliases
        yield self.columns
        yield self.column_instance
        yield self.drill_paths
        yield self.folders_common
        yield self.date_options
        yield self.extract

    def __get_section(self, obj, enforce_list=False):
        """ Sets DatasourceItems for each section

        Args:
            obj (type[tfo.TableauFileObject]): A Tableau File Object; ParentConnection, Column, etc
            enforce_list (bool): True if the section should be a TableauFileObjects list
        """
        parent = self._root.find('.')
        # Gets elements within the parent element, with the appropriate section.tag
        section: list[dict] = list()
        for element in parent:
            if element.tag.endswith(f'true...{obj.tag}') or element.tag == obj.tag:
                item = xmltodict.parse(ET.tostring(element))[element.tag]
                if not item:
                    continue
                new_item = transform_tableau_object(item)
                try:
                    section.append(obj(**new_item))
                except TypeError as err:
                    raise TableauFileError(f'{err}\n\nPre-transform {obj.tag} attributes: {item}') from err
        if len(section) > 1 or len(section) == 1 and enforce_list:
            return tfo.TableauFileObjects(section, item_class=obj, tag=obj.tag)
        elif len(section) == 1:
            return section[0]
        elif enforce_list:
            return tfo.TableauFileObjects(item_class=obj, tag=obj.tag)
        return obj()

    def enforce_column(self, column, folder_name=None, remote_name=None):
        """
            Enforces a column by:
                - Adding the column if it doesn't exist, otherwise updating it to match the column
                - Adding the column's corresponding folder-item to the appropriate folder, if it doesn't exist
                    - Create the folder if it doesn't exist
                - Updating the metadata local-name to map to the column name
                - Adding the column mapping to the mapping cols, if it doesn't exist

        Args:
            column (tfo.Column): The TableFile Column object
            remote_name (str): The name of the column from the connection (not required for Tableau Calculations),
             i.e. the SQL alias if the connection is a SQL query
            folder_name (str): The name of the folder that the column should be in

        """
        # Add Column
        if column not in self.columns:
            self.columns.add(column)
        # Update the Column
        else:
            self.columns.update(column)
        # Add Folder / FolderItem for the column, if folder_name was provided
        if folder_name:
            # Remove the column's folder-item for preview folder, if it will be moved to a new folder
            current_folder = [f for f in self.folders_common.folder if f.folder_item.get(column.name)]
            if current_folder and current_folder[0].name != folder_name:
                current_folder[0].folder_item.delete(column.name)
                self.folders_common.folder.update(current_folder[0])
            # Add column to the specified folder
            folder = self.folders_common.folder.get(folder_name)
            folder_item = tfo.FolderItem(name=column.name)
            if folder and folder_item not in folder.folder_item:
                folder.folder_item.append(folder_item)
                self.folders_common.folder.update(folder)
            elif not folder:
                self.folders_common.folder.add(tfo.Folder(name=folder_name, folder_item=[folder_item]))
        # If a remote_name was provided, and the column is not a Tableau Calculation - enforce metadata
        if remote_name and not column.calculation:
            # Update MetadataRecords
            datasource_record = self.connection.metadata_records.get(remote_name)
            datasource_record.local_name = column.name
            self.connection.metadata_records.update(datasource_record)
            extract_record = self.extract.connection.metadata_records.get(remote_name)
            if extract_record:
                extract_record.local_name = column.name
                self.extract.connection.metadata_records.update(extract_record)
            # Update MappingCols
            if column.name not in self.connection.cols:
                self.connection.cols.append(
                    tfo.MappingCol(key=column.name, value=f'{datasource_record.parent_name}.[{remote_name}]')
                )
            if column.name not in self.extract.connection.cols and extract_record:
                self.extract.connection.cols.append(
                    tfo.MappingCol(key=column.name, value=f'{extract_record.parent_name}.[{remote_name}]')
                )

    def save(self):
        """ Save all changes made to each section of the Datasource """
        parent = self._root.find('.')
        ending_index = -1
        for section in self.sections():
            if not section:
                continue
            # Find all elements within the parent element, and the index of those elements
            elements = [(idx, element)
                        for idx, element in enumerate(parent)
                        if element.tag.endswith(f'true...{section.tag}') or element.tag == section.tag]
            # If there are no existing element(s), the index will be for the previous ending_index (default == -1)
            starting_index = elements[0][0] if elements else ending_index
            ending_index = elements[-1][0] + 1 if elements else starting_index
            # Remove the existing items
            for _, e in elements:
                parent.remove(e)
            # Insert the new / updated items
            if isinstance(section, tfo.TableauFileObjects):
                section.reverse()
                for idx, item in enumerate(section, 1):
                    parent.insert(starting_index, item.xml())
                    ending_index = starting_index + idx
            else:
                parent.insert(starting_index, section.xml())
        super().save()


if __name__ == '__main__':
    # Params
    ds_path = 'downloads/Users + Orgs.tdsx'

    unzip = False
    unzip_all_files = False

    ds = Datasource(ds_path)
    if unzip:
        ds.unzip(unzip_all=unzip_all_files)

    print(ds.columns.get('[USER_ID]'))

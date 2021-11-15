import pymongo
import pandas as pd
import time
from src.utils.common.common_helper import read_config
from src.utils.common.common_helper import check_file_presence
import os
from loguru import logger

config_args = read_config("config.yaml")
log_path = os.path.join(".", config_args['logs']['logger'], config_args['logs']['generallogs_file'])
logger.add(sink=log_path, format="[{time:YYYY-MM-DD HH:mm:ss.SSS} - {level} - {module} ] - {message}", level="INFO")


class MongoHelper:

    def __init__(self):
        try:
            path = config_args['secrets']['mongo']
            self.client = pymongo.MongoClient(path)
            self.db = self.client['Auto-neuron']
            logger.info("Mongodb Connection Established")
        except Exception as e:
            logger.error(e)

    def create_new_project(self, collection_name, df):
        """[summary]
            Create New Project and Upload data
        Args:
            collection_name ([type]): [description]
            df ([type]): [description]
        """
        try:
            collection = self.db[collection_name]
            df.reset_index(inplace=True)
            begin = time.time()
            
            self.delete_collection_data(collection_name)
            rec = collection.insert_many(df.to_dict('records'))
            end = time.time()
            logger.info(f"Your data is uploaded. Total time taken: {end - begin} seconds.")
            
            if rec:
                return len(rec.inserted_ids)
            return 0
        except Exception as e:
            logger.error(e)
        
    def delete_collection_data(self, collection_name):
        """[summary]
        Delete Collection Data
        Args:
            collection_name ([type]): [description]
        """
        try:
            begin = time.time()
            collection = self.db[collection_name]
            collection.delete_many({})
            end = time.time()  
            logger.info(f"All records deleted. Total time taken: {end - begin} seconds.")
        except Exception as e:
            logger.error(e)
            
    def get_collection_data(self, project_name):
        """[summary]
            Get Collection Data
        Args:
            project_name ([type]): [description]

        Returns:
            [type]: [description]
        """
        try:
            path = os.path.join(os.path.join('src', 'data'), f"{project_name}.csv")
            backup_path = os.path.join(os.path.join('src', 'data'), f"{project_name}_backup.csv")
            if os.path.exists(path):
                df = pd.read_csv(path)
                return df
            else:
                begin = time.time()
                collection = self.db[project_name]
                df = pd.DataFrame(list(collection.find()))
                end = time.time()
                logger.info(f"All records deleted. Total time taken: {end - begin} seconds.")
                df.to_csv(path)
                df.to_csv(backup_path)
                return df

        except Exception as e:
            logger.error(e)

    def download_collection_data(self, project_id, file_type):
        """This function downloads user dataset from mongodb and converts it to required file type, before downloading
        it checks if file exist locally or not, if it exist it will not download instead takes tht file and converts
        into required file type
                    download_collection_data
                Args:
                    project_id (str): project_id is the collection name of user dataset
                    file_type (str): required output file type eg:csv, tsv, json, xlsx

                Returns:
                    download status (str) : Successful or Unsuccessful
                    path : file path of newly created file
                """
        try:
            path = os.path.join(os.path.join('src', 'temp_data_store'), f"{project_id}.{file_type}")
            if check_file_presence(project_id)[0]:
                print("File Exist!!")
                df = check_file_presence(project_id)[1]
                try:
                    df.drop(columns=['_id'], inplace=True)
                except Exception as e:
                    pass

            else:
                begin = time.time()
                collection = self.db[project_id]
                df = pd.DataFrame(list(collection.find()))
                end = time.time()
                df.drop(columns=['_id'], inplace=True)
                print(f"Downloded {project_id} collection data from database. Total time taken: {end - begin} seconds.")

            if file_type == 'csv':
                df.to_csv(path)
            elif file_type == 'tsv':
                df.to_csv(path, sep='\t')
            elif file_type == 'json':
                df.to_json(path)
            elif file_type == 'xlsx':
                print("excel")
                df.to_excel(path)
            download_status = 'Successful'
            return download_status, path

        except Exception as e:
            print(e.__str__())
            download_status = "Unsuccessful"
            return download_status, path

    def drop_collection(self, collection_name):
        """[summary]
        Delete Collection from mongo
        Args:
            collection_name ([type]): [description]
        """
        try:
            begin = time.time()
            collection = self.db[collection_name]
            collection.drop()
            end = time.time()
            print(f"Dropped {collection_name} collection from database. Total time taken: {end - begin} seconds.")
        except Exception as e:
            print(e)


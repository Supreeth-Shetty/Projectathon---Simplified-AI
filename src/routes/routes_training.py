from flask import Blueprint, redirect, url_for, render_template, request, session
from src.constants.model_params import Ridge_Params, Lasso_Params, ElasticNet_Params, RandomForestRegressor_Params, \
    SVR_params, AdabootRegressor_Params, \
    GradientBoostRegressor_Params
from src.constants.model_params import KmeansClustering_Params, DbscanClustering_Params, AgglomerativeClustering_Params
from src.constants.model_params import LogisticRegression_Params, SVC_Params, KNeighborsClassifier_Params, \
    DecisionTreeClassifier_Params, RandomForestClassifier_Params, GradientBoostingClassifier_Params, \
    AdaBoostClassifier_Params
from src.constants.constants import ACTIVATION_FUNCTIONS, CLASSIFICATION_MODELS, CLUSTERING_MODELS, OPTIMIZERS, \
    REGRESSION_LOSS
from flask.json import jsonify
from src.constants.model_params import DecisionTreeRegressor_Params, LinearRegression_Params
from src.model.custom.classification_models import ClassificationModels
from src.model.custom.regression_models import RegressionModels
from src.model.custom.clustering_models import ClusteringModels
from src.preprocessing.preprocessing_helper import Preprocessing
from src.constants.constants import REGRESSION_MODELS
from src.utils.common.prediction_helper import make_prediction
from src.utils.databases.mysql_helper import MySqlHelper
from werkzeug.utils import secure_filename
import os
from src.utils.common.common_helper import get_param_value, load_prediction_result, load_project_model, \
    read_config, save_prediction_result, save_project_model
import pandas as pd
from src.utils.common.data_helper import load_data
from src.model.auto.Auto_classification import ModelTrain_Classification
from src.model.auto.Auto_regression import ModelTrain_Regression
from src.feature_engineering.feature_engineering_helper import FeatureEngineering
from loguru import logger
from from_root import from_root
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error, accuracy_score, precision_score, \
    f1_score, recall_score
from src.utils.common.project_report_helper import ProjectReports

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
import numpy as np
from sklearn.model_selection import train_test_split

app_training = Blueprint('training', __name__)

config_args = read_config("./config.yaml")

mysql = MySqlHelper.get_connection_obj()

log_path = os.path.join(from_root(), config_args['logs']['logger'], config_args['logs']['generallogs_file'])
logger.add(sink=log_path, format="[{time:YYYY-MM-DD HH:mm:ss.SSS} - {level} - {module} ] - {message}", level="INFO")


@app_training.route('/model_training/<action>', methods=['GET'])
def model_training(action):
    try:
        if 'pid' in session:
            df = load_data()
            if df is not None:
                target_column = ""
                if session['target_column'] is not None:
                    target_column = session['target_column']

                target_column = session['target_column']
                cols_ = [col for col in df.columns if col != target_column]
                # Check data contain any categorical independent features
                Categorical_columns = Preprocessing.col_seperator(df.loc[:, cols_], "Categorical_columns")
                if len(Categorical_columns.columns) > 0:
                    return render_template('model_training/auto_training.html', project_type=session['project_type'],
                                           target_column=session['target_column'], status="error",
                                           msg="Data contain some categorical indepedent features, please perform encoding first")

                """Check If Project type is Regression or Classificaion and target Columns is not Selected"""
                if session['project_type'] != 3 and session['target_column'] is None:
                    return redirect('/target-column')

                if action == 'help':
                    return render_template('model_training/help.html')
                elif action == 'auto_training':
                    logger.info('Redirect To Auto Training Page')
                    ProjectReports.insert_record_ml('Redirect To Auto Training Page')

                    if session['project_type'] == 3:
                        return render_template('model_training/auto_training.html',
                                               project_type=session['project_type'],
                                               target_column=session['target_column'], status="error",
                                               msg="Auto Training is not available for Clustering!!!")

                    return render_template('model_training/auto_training.html', project_type=session['project_type'],
                                           target_column=session['target_column'])

                elif action == 'custom_training' or action == 'final_train_model':
                    query = f""" select a.pid ProjectId , a.TargetColumn TargetName, 
                                                   a.Model_Name ModelName, 
                                                   b.Schedule_date, 
                                                   b.schedule_time ,
                                                   a.Model_Trained, 
                                                   b.train_status ,
                                                   b.email, 
                                                   b.deleted
                                                   from tblProjects as a
                                                   join tblProject_scheduler as b on a.Pid = b.ProjectId where b.ProjectId = '{session.get('project_name')}' 
                                                   and b.deleted=0
                                                   """
                    result = mysql.fetch_one(query)

                    if result is not None:
                        return render_template('scheduler/training_blocker.html')

                    logger.info('Redirect To Custom Training Page')
                    ProjectReports.insert_record_ml('Redirect To Custom Training Page')

                    try:
                        if session['project_type'] == 2:
                            return render_template('model_training/classification.html', action=action,
                                                   models=CLASSIFICATION_MODELS)
                        elif session['project_type'] == 1:
                            return render_template('model_training/regression.html', action=action,
                                                   models=REGRESSION_MODELS)
                        elif session['project_type'] == 3:
                            return render_template('model_training/clustering.html', action=action,
                                                   models=CLUSTERING_MODELS)
                        else:
                            return render_template('model_training/custom_training.html')
                    except Exception as e:
                        logger.error(e)
                        return render_template('model_training/custom_training.html')
                else:
                    return 'Non-Implemented Action'
            else:
                return redirect('/')
        else:
            return redirect(url_for('/'))
    except Exception as e:
        logger.error('Error in Model Training')
        ProjectReports.insert_record_ml('Error in Model Training', '', '', 0, str(e))
        return render_template('500.html', exception=e)


@app_training.route('/model_training/<action>', methods=['POST'])
def model_training_post(action):
    try:
        if 'pid' in session:
            df = load_data()
            model = None
            range = None
            random_state = None
            if df is not None:
                if action == 'help':
                    return render_template('model_training/help.html')
                elif action == 'custom_training':
                    try:
                        model = request.form['model']
                        range = int(request.form['range'])

                        if model != "KNeighborsClassifier" and model != "SVR":
                            random_state = int(request.form['random_state'])

                        logger.info('Submitted Custom Training Page')
                        ProjectReports.insert_record_ml('Submitted Custom Training Page',
                                                        f"Model:{model}; Range:{range}; Random_State: {random_state}")

                        target = session['target_column']
                        if session['project_type'] != 3:
                            X = df.drop(target, axis=1)
                            y = df[target]
                            train_model_fun = None
                            X_train, X_test, y_train, y_test = FeatureEngineering.train_test_Split(cleanedData=X,
                                                                                                   label=y,
                                                                                                   train_size=range / 100,
                                                                                                   random_state=random_state)

                            model_params = {}
                            if model == "LinearRegression":
                                Model_Params = LinearRegression_Params
                                train_model_fun = RegressionModels.linear_regression_regressor
                            elif model == "Ridge":
                                Model_Params = Ridge_Params
                                train_model_fun = RegressionModels.ridge_regressor
                            elif model == "Lasso":
                                Model_Params = Lasso_Params
                                train_model_fun = RegressionModels.lasso_regressor
                            elif model == "ElasticNet":
                                Model_Params = ElasticNet_Params
                                train_model_fun = RegressionModels.elastic_net_regressor
                            elif model == "DecisionTreeRegressor":
                                Model_Params = DecisionTreeRegressor_Params
                                train_model_fun = RegressionModels.decision_tree_regressor
                            elif model == "RandomForestRegressor":
                                Model_Params = RandomForestRegressor_Params
                                train_model_fun = RegressionModels.random_forest_regressor
                            elif model == "SVR":
                                Model_Params = SVR_params
                                train_model_fun = RegressionModels.support_vector_regressor
                            elif model == "AdaBoostRegressor":
                                Model_Params = AdabootRegressor_Params
                                train_model_fun = RegressionModels.ada_boost_regressor
                            elif model == "GradientBoostingRegressor":
                                Model_Params = GradientBoostRegressor_Params
                                train_model_fun = RegressionModels.gradient_boosting_regressor
                            elif model == "LogisticRegression":
                                Model_Params = LogisticRegression_Params
                                train_model_fun = ClassificationModels.logistic_regression_classifier
                            elif model == "SVC":
                                Model_Params = SVC_Params
                                train_model_fun = ClassificationModels.support_vector_classifier
                            elif model == "KNeighborsClassifier":
                                print('here')
                                Model_Params = KNeighborsClassifier_Params
                                train_model_fun = ClassificationModels.k_neighbors_classifier
                            elif model == "DecisionTreeClassifier":
                                Model_Params = DecisionTreeClassifier_Params
                                train_model_fun = ClassificationModels.decision_tree_classifier
                            elif model == "RandomForestClassifier":
                                Model_Params = RandomForestClassifier_Params
                                train_model_fun = ClassificationModels.random_forest_classifier
                            elif model == "AdaBoostClassifier":
                                Model_Params = AdaBoostClassifier_Params
                                train_model_fun = ClassificationModels.ada_boost_classifier
                            elif model == "GradientBoostClassifier":
                                Model_Params = GradientBoostingClassifier_Params
                                train_model_fun = ClassificationModels.gradient_boosting_classifier
                            else:
                                return 'Non-Implemented Action'

                            for param in Model_Params:
                                model_params[param['name']] = get_param_value(param, request.form[param['name']])
                            trained_model = train_model_fun(X_train, y_train, True, **model_params)

                            """Save Trained Model"""
                            save_project_model(trained_model)

                            reports = [{"key": "Model Name", "value": model},
                                       {"key": "Data Size", "value": len(df)},
                                       {"key": "Trained Data Size", "value": len(X_train)},
                                       {"key": "Test Data Size", "value": len(X_test)}]

                            scores = []
                            # Regression
                            if trained_model is not None and session['project_type'] == 1:
                                y_pred = trained_model.predict(X_test)
                                scores.append({"key": "r2_score", "value": r2_score(y_test, y_pred)})
                                scores.append(
                                    {"key": "mean_absolute_error", "value": mean_absolute_error(y_test, y_pred)})
                                scores.append(
                                    {"key": "mean_squared_error", "value": mean_squared_error(y_test, y_pred)})
                                # Model Name Set in table while training
                                query = f'''Update tblProjects Set Model_Name="{model}", Model_Trained=0 Where Id="{session.get('pid')}"'''
                                mysql.update_record(query)

                                return render_template('model_training/model_result.html', action=action,
                                                       status="success",
                                                       reports=reports, scores=scores, model_params=model_params)

                            # Classification
                            if trained_model is not None and session['project_type'] == 2:
                                y_pred = trained_model.predict(X_test)
                                scores.append({"key": "Accuracy", "value": accuracy_score(y_test, y_pred)})
                                scores.append({"key": "Classes", "value": df[target].unique()})
                                scores.append(
                                    {"key": "Precision", "value": precision_score(y_test, y_pred, average=None)})
                                scores.append({"key": "Recall", "value": recall_score(y_test, y_pred, average=None)})
                                scores.append({"key": "F1_score", "value": f1_score(y_test, y_pred, average=None)})

                                # Model Name Set in table while training
                                query = f'''Update tblProjects Set Model_Name="{model}", Model_Trained=0 Where Id="{session.get('pid')}"'''
                                result = mysql.update_record(query)
                                return render_template('model_training/model_result.html', action=action,
                                                       status="success",
                                                       reports=reports, scores=scores, model_params=model_params)
                        elif session['project_type'] == 3:
                            X = df
                            train_model_fun = None
                            model_params = {}
                            if model == "KMeans":
                                Model_Params = KmeansClustering_Params
                                train_model_fun = ClusteringModels.kmeans_clustering
                            elif model == "DBSCAN":
                                Model_Params = DbscanClustering_Params
                                train_model_fun = ClusteringModels.dbscan_clustering
                            elif model == "AgglomerativeClustering":
                                Model_Params = AgglomerativeClustering_Params
                                train_model_fun = ClusteringModels.agglomerative_clustering
                            else:
                                return 'Non-Implemented Action'

                            for param in Model_Params:
                                model_params[param['name']] = get_param_value(param, request.form[param['name']])

                            trained_model, y_pred = train_model_fun(X, True, **model_params)
                            """Save Trained Model"""
                            save_project_model(trained_model)

                            reports = [{"key": "Model Name", "value": model},
                                       {"key": "Data Size", "value": len(df)},
                                       {"key": "Train Data Size", "value": len(X)},
                                       {"key": "Test Data Size", "value": 0}]

                            scores = []

                            # Clustering
                            if trained_model is not None and session['project_type'] == 3:
                                scores.append({"key": "Predicted Classes",
                                               "value": pd.DataFrame(data=y_pred, columns=['y_pred'])[
                                                   'y_pred'].unique()})

                                # Model Name Set in table while training
                                query = f'''Update tblProjects Set Model_Name="{model}", Model_Trained=0 Where Id="{session.get('pid')}"'''
                                result = mysql.update_record(query)
                                return render_template('model_training/model_result.html', action=action,
                                                       status="success",
                                                       reports=reports, scores=scores, model_params=model_params)
                            else:
                                raise Exception("Model Couldn't train, please check parametes")

                    except Exception as e:
                        logger.error('Error Submitted Custom Training Page')
                        ProjectReports.insert_record_ml('Error Submitted Custom Training Page',
                                                        f"Model:{model}; Range:{range}; Random_State: {random_state}",
                                                        '', 0, str(e))
                        if session['project_type'] == 2:
                            return render_template('model_training/classification.html', action=action,
                                                   models=CLASSIFICATION_MODELS, status="error", msg=str(e))
                        elif session['project_type'] == 1:
                            return render_template('model_training/regression.html', action=action,
                                                   models=REGRESSION_MODELS, status="error", msg=str(e))
                        else:
                            return render_template('model_training/clustering.html', action=action,
                                                   models=CLUSTERING_MODELS, status="error", msg=str(e))

                elif action == "auto_training":
                    try:
                        target = session['target_column']
                        if target is None:
                            return redirect(url_for('/target-column'))

                        # data_len = len(df)
                        # data_len = 10000 if data_len > 10000 else int(len(df) * 0.9)

                        # df = df.sample(frac=1).loc[:data_len, :]
                        trainer = None
                        X = df.drop(target, axis=1)
                        y = df[target]
                        X_train, X_test, y_train, y_test = FeatureEngineering.train_test_Split(cleanedData=X,
                                                                                               label=y,
                                                                                               train_size=0.75,
                                                                                               random_state=101)
                        if session['project_type'] == 1:
                            trainer = ModelTrain_Regression(X_train, X_test, y_train, y_test, True)
                            result = trainer.results()
                            result = result.to_html()
                            return render_template('model_training/auto_training.html', status="success",
                                                   project_type=session['project_type'],
                                                   target_column=session['target_column'], train_done=True,
                                                   result=result)

                        elif session['project_type'] == 2:
                            trainer = ModelTrain_Classification(X_train, X_test, y_train, y_test, True)
                            result = trainer.results()

                            result = result.to_html()
                            return render_template('model_training/auto_training.html', status="success",
                                                   project_type=session['project_type'],
                                                   target_column=session['target_column'], train_done=True,
                                                   result=result)
                    except Exception as ex:
                        return render_template('model_training/auto_training.html', status="error",
                                               project_type=session['project_type'],
                                               target_column=session['target_column'], msg=str(ex))

                elif action == 'final_train_model':
                    try:
                        logger.info('Final Train Model')
                        ProjectReports.insert_record_ml('Final Train Model')
                        query = f'''select Model_Name from tblProjects Where Id="{session.get('pid')}"'''
                        model_name = mysql.fetch_one(query)[0]

                        if session['project_type'] != 3:
                            target = session['target_column']
                            X = df.drop(target, axis=1)
                            y = df[target]
                            model = load_project_model()
                            if model is None:
                                return render_template('model_training/model_result.html', action=action,
                                                       status="error",
                                                       msg="Model is not found, please train model again")
                            else:
                                model_params = {}
                                for key, value in model.get_params().items():
                                    model_params[key] = value
                                if model_name == "LinearRegression":
                                    train_model_fun = RegressionModels.linear_regression_regressor
                                elif model_name == "Ridge":
                                    train_model_fun = RegressionModels.ridge_regressor
                                elif model_name == "Lasso":
                                    train_model_fun = RegressionModels.lasso_regressor
                                elif model_name == "ElasticNet":
                                    train_model_fun = RegressionModels.elastic_net_regressor
                                elif model_name == "DecisionTreeRegressor":
                                    train_model_fun = RegressionModels.decision_tree_regressor
                                elif model_name == "RandomForestRegressor":
                                    train_model_fun = RegressionModels.random_forest_regressor
                                elif model_name == "SVR":
                                    train_model_fun = RegressionModels.support_vector_regressor
                                elif model_name == "AdaBoostRegressor":
                                    train_model_fun = RegressionModels.ada_boost_regressor
                                elif model_name == "GradientBoostingRegressor":
                                    train_model_fun = RegressionModels.gradient_boosting_regressor
                                elif model_name == "LogisticRegression":
                                    train_model_fun = ClassificationModels.logistic_regression_classifier
                                elif model_name == "SVC":
                                    train_model_fun = ClassificationModels.support_vector_classifier
                                elif model_name == "KNeighborsClassifier":
                                    train_model_fun = ClassificationModels.k_neighbors_classifier
                                elif model_name == "DecisionTreeClassifier":
                                    train_model_fun = ClassificationModels.decision_tree_classifier
                                elif model_name == "RandomForestClassifier":
                                    train_model_fun = ClassificationModels.random_forest_classifier
                                elif model_name == "AdaBoostClassifier":
                                    train_model_fun = ClassificationModels.ada_boost_classifier
                                elif model_name == "GradientBoostClassifier":
                                    train_model_fun = ClassificationModels.gradient_boosting_classifier
                                else:
                                    return 'Non-Implemented Action'

                                trained_model = train_model_fun(X, y, True, **model_params)

                                """Save Final Model"""
                                save_project_model(trained_model, 'model.pkl')
                                query = f'''Update tblProjects Set Model_Trained=1 Where Id="{session.get('pid')}"'''
                                mysql.update_record(query)
                                logger.info('Final Training Done')
                                ProjectReports.insert_record_ml('Final Training Done')

                                return render_template('model_training/congrats.html')

                        elif session['project_type'] == 3:
                            X = df
                            model = load_project_model()
                            if model is None:
                                return render_template('model_training/model_result.html', action=action,
                                                       status="error",
                                                       msg="Model is not found, please train model again")
                            else:
                                model_params = {}
                                for key, value in model.get_params().items():
                                    model_params[key] = value
                                if model_name == "KMeans":
                                    train_model_fun = ClusteringModels.kmeans_clustering
                                elif model_name == "DBSCAN":
                                    train_model_fun = ClusteringModels.dbscan_clustering
                                elif model_name == "AgglomerativeClustering":
                                    train_model_fun = ClusteringModels.agglomerative_clustering
                                else:
                                    return 'Non Implemented mtd'

                                trained_model, y_pred = train_model_fun(X, True, **model_params)

                                """Save Trained Model"""
                                save_project_model(trained_model, 'model.pkl')
                                query = f'''Update tblProjects Set Model_Trained=1 Where Id="{session.get('pid')}"'''
                                mysql.update_record(query)
                                logger.info('Final Training Done')
                                ProjectReports.insert_record_ml('Final Training Done')

                                return render_template('model_training/congrats.html')

                    except Exception as e:
                        logger.error('Error in Model Training Submit')
                        ProjectReports.insert_record_ml('Error in Model Training', '', '', 0, str(e))
                        render_template('model_training/model_result.html', action=action, status="error",
                                        msg="Model is not found, please train model again")

                if action == "Scheduled_model":
                    path = os.path.join(from_root(), 'artifacts', 'model_temp.pkl')
                    pass

                else:
                    return "Non Implemented Method"
        else:
            logger.critical('DataFrame has no data')
            return redirect('/')
    except Exception as e:
        logger.error('Error in Model Training Submit')
        ProjectReports.insert_record_ml('Error in Model Training', '', '', 0, str(e))
        return render_template('500.html', exception=e)


@app_training.route('/congrats', methods=['GET', 'POST'])
def congrats():
    try:
        if 'pid' in session:
            df = load_data()
            if df is not None:
                target = session['target_column']
                X = df.drop(target, axis=1)
                y = df[target]
                model = load_project_model()
                if model is None:
                    return render_template('model_training/model_result.html', status="error",
                                           msg="Model is not found, please train model again")
                else:
                    for key, value in model.get_params():
                        exec(key + "=value")

            logger.info('Loaded Congrats Page')
            ProjectReports.insert_record_ml('Loaded Congrats Page')
            if request.method == "GET":
                return render_template('model_training/congrats.html')
            else:
                return render_template('model_training/congrats.html')
    except Exception as e:
        logger.error('Error in Model Training Submit')
        ProjectReports.insert_record_ml('Error in Model Training', '', '', 0, str(e))
        return render_template('500.html', exception=e)


@app_training.route('/prediction', methods=['GET', 'POST'])
def prediction():
    try:
        if 'pid' in session:
            file_path = ""
            logger.info('Loaded Prediction Page')
            ProjectReports.insert_record_ml('Loaded Prediction Page')
            if request.method == "GET":
                is_trained = mysql.fetch_all(
                    f"SELECT * FROM tblProjects WHERE Id ={session.get('pid')} AND Model_Trained=1")
                if is_trained is None:
                    return render_template('model_training/prediction_page.html', status="error",
                                           msg="your model is not trained, please train model first")
                else:
                    return render_template('model_training/prediction_page.html', status="success")
            else:
                try:

                    f = request.files['file']
                    ALLOWED_EXTENSIONS = ['csv', 'tsv', 'json']
                    msg = ""
                    if len(request.files) == 0:
                        msg = 'Please select a file to upload'
                    elif f.filename.strip() == '':
                        msg = 'Please select a file to upload'
                    elif f.filename.rsplit('.', 1)[1].lower() not in ALLOWED_EXTENSIONS:
                        msg = 'This file format is not allowed, please select mentioned one'

                    if msg:
                        logger.error(msg)
                        return render_template('model_training/prediction_page.html', status="error", msg=msg)

                    filename = secure_filename(f.filename)
                    file_path = os.path.join(config_args['dir_structure']['upload_folder'], filename)
                    f.save(file_path)

                    if file_path.endswith('.csv'):
                        df = pd.read_csv(file_path)
                    elif file_path.endswith('.tsv'):
                        df = pd.read_csv(file_path, sep='\t')
                    elif file_path.endswith('.json'):
                        df = pd.read_json(file_path)
                    else:
                        msg = 'This file format is currently not supported'
                        logger.info(msg)
                        return render_template('model_training/prediction_page.html', status="error", msg=msg)

                    prediction = make_prediction(df)
                    data = prediction.to_html()

                    if len(data) > 0:
                        save_prediction_result(prediction)
                        return render_template('model_training/prediction_result.html', status="success", data=data)
                    else:
                        return render_template('model_training/prediction_result.html', status="error",
                                               msg="There is some issue, coudn't perform prediction. Please check your data")
                except Exception as e:
                    logger.error('Error in Model Training Submit')
                    ProjectReports.insert_record_ml('Error in Model Training', '', '', 0, str(e))
                    return render_template('model_training/prediction_page.html', status="error", msg=str(e))
                finally:
                    if file_path:
                        os.remove(file_path)
        else:
            logger.error('Project id not found, redirect to home page')
            ProjectReports.insert_record_ml('Project id not found, redirect to home page', '', '', 0, 'Error')
            return redirect('/')
    except Exception as e:
        logger.error(e)
        return redirect('/')


@app_training.route('/download_prediction', methods=['POST'])
def download_prediction():
    try:
        return load_prediction_result()

    except Exception as e:
        logger.error(e)
        return jsonify({'success': False})


@app_training.route('/model_training/ann', methods=['GET'])
def ann_training():
    try:
        return render_template('model_training/ann.html', optimizers=OPTIMIZERS,
                               activation_functions=ACTIVATION_FUNCTIONS, loss=REGRESSION_LOSS)

    except Exception as e:
        logger.error(e)
        return jsonify({'success': False})


def create_layers(data=None, df=None, feature_map={}, typ=None):
    layers = []

    infer_in = data[0]['units']

    for i in data:
        if i['type'] == 'input':
            in_feature = df.shape[1]
            out_feature = i['units']

            layers.append(nn.Linear(in_features=in_feature, out_features=out_feature))

            if i['activation'] == 'ReLU':
                layers.append(nn.ReLU())

            elif i['activation'] == 'ELU':
                layers.append(nn.ELU())

            elif i['activation'] == 'LeakyReLU':
                layers.append(nn.LeakyReLU())

            elif i['activation'] == 'LeakyReLU':
                layers.append(nn.LeakyReLU())

            elif i['activation'] == 'Softmax':
                layers.append(nn.Softmax())

            elif i['activation'] == 'PReLU':
                layers.append(nn.PReLU())

            elif i['activation'] == 'SELU':
                layers.append(nn.SELU())

            elif i['activation'] == 'Tanh':
                layers.append(nn.Tanh())

            elif i['activation'] == 'Softplus':
                layers.append(nn.Softplus())

            elif i['activation'] == 'Softmin':
                layers.append(nn.Softmin())

            elif i['activation'] == 'Sigmoid':
                layers.append(nn.Sigmoid())

            elif i['activation'] == 'RReLU':
                layers.append(nn.RReLU())

            else:
                layers.append(nn.ReLU())

        if i['type'] == 'linear':
            in_feature = infer_in
            out_feature = i['units']
            layers.append(nn.Linear(in_feature, out_feature))
            infer_in = out_feature

        if i['type'] == 'batch_normalize':
            layers.append(nn.BatchNorm1d(num_features=infer_in))

        if i['type'] == 'dropout':
            layers.append(nn.Dropout(p=i['percentage']))

        if i['type'] == 'output':
            if typ == 'Regression':
                in_feature = infer_in
                out_feature = 1
                layers.append(nn.Linear(in_features=in_feature, out_features=out_feature))

            if typ == 'Classification':
                in_feature = infer_in
                out_feature = len(feature_map.keys())
                layers.append(nn.Linear(in_features=in_feature, out_features=out_feature))

            if typ == 'cluestring':
                return 'CLuestring cant be performed using Ann'

    return layers


class CustomTrainData(Dataset):
    def __init__(self, train_df, target):
        self.train_df = train_df
        self.target = target
        self.x = torch.from_numpy(self.train_df.to_numpy())
        self.y = torch.from_numpy(self.target.to_numpy())
        self.n_sample = self.train_df.shape[0]

    def __getitem__(self, index):
        return self.x[index], self.y[index]

    def __len__(self):
        return self.n_sample


class CustomTestData(Dataset):
    def __init__(self, test_df, target):
        self.test_df = test_df
        self.target = target
        self.x = torch.from_numpy(self.test_df.to_numpy())
        self.y = torch.from_numpy(self.target.to_numpy())
        self.n_sample = self.test_df.shape[0]

    def __getitem__(self, index):
        return self.x[index], self.y[index]

    def __len__(self):
        return self.n_sample


def trainTestSplit(df, target, size=0.25):
    X = df.drop(target, axis=1)
    y = df[target]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=1 - size, random_state=101)

    return X_train, X_test, y_train, y_test


def main(Data=None, df=None, target=None, size=None, num_epoch=None, typ=None):
    # Train test Split
    feature_map = {}
    if typ == 'Classification':

        for i in enumerate(df[target].unique()):
            feature_map[i[1]] = i[0]

        df[target] = df[target].replace(feature_map)

    X_train, X_test, y_train, y_test = trainTestSplit(df, target, size=size)

    # Data class creation
    trainData = CustomTrainData(X_train, y_train)
    testData = CustomTestData(X_test, y_test)

    # Data loader creation
    train_data_loader = DataLoader(trainData, batch_size=32, shuffle=True)
    test_data_loader = DataLoader(testData, batch_size=32)

    print(feature_map)
    # Model Creation
    model = nn.Sequential(*create_layers(Data, X_train, feature_map, typ))
    # Optimizer and Loss ---- > front end
    print(model)
    if typ == "Classification":
        loss_func = nn.CrossEntropyLoss()

    if typ == "Regression":
        loss_func = nn.MSELoss()

    optimizer = torch.optim.Adam(model.parameters())

    # Regression
    # Train
    loss_perEpoch = []
    if typ == "Regression":
        model.train()
        num_epochs = num_epoch
        for epooch in range(num_epochs):
            for batch_idx, data in enumerate(train_data_loader):
                features = data[0].float()
                labels = data[1].float()
                # print(features.shape,labels.shape)
                optimizer.zero_grad()

                output = model(features)
                loss = loss_func(output, labels)

                loss.backward()
                optimizer.step()

                if batch_idx % 2 == 0:
                    loss_perEpoch.append(loss.item())
                    print(f'Epoch {epooch}/{num_epochs}  Loss: {loss.item()}')

        # Test
        model.eval()
        test_loss = []

        with torch.no_grad():
            for idx, data in enumerate(test_data_loader):
                features = data[0].float()
                labels = data[1].float()

                output = model(features)
                test_loss.append(loss_func(output, labels).item())

        print("Test Accuracy :", np.mean(test_loss))

    # Classification
    if typ == 'Classification':
        # Train
        model.train()
        num_epochs = num_epoch
        for epooch in range(num_epochs):
            for batch_idx, data in enumerate(train_data_loader):
                features = data[0].float()
                labels = data[1]
                # print(features,labels)
                optimizer.zero_grad()

                output = model(features)
                loss = loss_func(output, labels)

                loss.backward()
                optimizer.step()

                if batch_idx % 8 == 0:
                    loss_perEpoch.append(loss.item())
                    print(f'Epoch {epooch}/{num_epochs} Loss: {loss.item()}')

        # Test
        model.eval()
        test_loss = []
        test_acc = []
        with torch.no_grad():
            for idx, data in enumerate(test_data_loader):
                features = data[0].float()
                labels = data[1]

                output = model(features)

                test_acc.append((torch.argmax(output, axis=1) == labels.squeeze().long()).float().mean())
                test_loss.append(loss_func(output, labels).item())

            print("Test Loss :", np.mean(test_loss), "  ", "Test Accuracy :", np.mean(test_acc))


@app_training.route('/model_training/ann', methods=['POST'])
def ann_model_training():
    try:

        data = request.get_json(force=True)
        print(data['layerUnits'])
        df = load_data()
        target = session['target_column']
        typ = 'Regression' if session['project_type'] == 1 else 'Classification'
        print(df.head())
        print(target)
        print(typ)
        main(data['layerUnits'], df, target=target, size=0.75, num_epoch=60, typ=typ)
        return jsonify({'success': True})

    except Exception as e:
        logger.error(e)
        return jsonify({'success': False})

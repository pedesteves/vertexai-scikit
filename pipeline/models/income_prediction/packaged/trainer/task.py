# [START setup]
import datetime
import os
import argparse

import pandas as pd

from google.cloud import storage

from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_selection import SelectKBest
from sklearn.pipeline import FeatureUnion
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelBinarizer
import joblib

parser = argparse.ArgumentParser(description='Process some integers.')
parser.add_argument('input_bucket')
parser.add_argument('input_file')
args = parser.parse_args()

input_bucket = args.input_bucket
input_file = args.input_file

gcs = storage.Client()
bucket = gcs.bucket(input_bucket)
blob = bucket.blob(input_file)
blob.download_to_filename('input.data')

# ---------------------------------------
# This is where your model code would go. Below is an example model using the census dataset.
# ---------------------------------------
# [START define-and-load-data]
# Define the format of your input data including unused columns (These are the columns from the census data files)
COLUMNS = (
    'age',
    'workclass',
    'fnlwgt',
    'education',
    'education-num',
    'marital-status',
    'occupation',
    'relationship',
    'race',
    'sex',
    'capital-gain',
    'capital-loss',
    'hours-per-week',
    'native-country',
    'income-level'
)

# Categorical columns are columns that need to be turned into a numerical value to be used by scikit-learn
CATEGORICAL_COLUMNS = (
    'workclass',
    'education',
    'marital-status',
    'occupation',
    'relationship',
    'race',
    'sex',
    'native-country'
)


# Load the training census dataset
with open('./input.data', 'r') as train_data:
    raw_training_data = pd.read_csv(train_data, header=None, names=COLUMNS)

# Remove the column we are trying to predict ('income-level') from our features list
# Convert the Dataframe to a lists of lists
train_features = raw_training_data.drop('income-level', axis=1).values.tolist()
# Create our training labels list, convert the Dataframe to a lists of lists
train_labels = (raw_training_data['income-level'] == ' >50K').values.tolist()
# [END define-and-load-data]


# [START categorical-feature-conversion]
# Since the census data set has categorical features, we need to convert
# them to numerical values. We'll use a list of pipelines to convert each
# categorical column and then use FeatureUnion to combine them before calling
# the RandomForestClassifier.
categorical_pipelines = []

# Each categorical column needs to be extracted individually and converted to a numerical value.
# To do this, each categorical column will use a pipeline that extracts one feature column via
# SelectKBest(k=1) and a LabelBinarizer() to convert the categorical value to a numerical one.
# A scores array (created below) will select and extract the feature column. The scores array is
# created by iterating over the COLUMNS and checking if it is a CATEGORICAL_COLUMN.
for i, col in enumerate(COLUMNS[:-1]):
    if col in CATEGORICAL_COLUMNS:
        # Create a scores array to get the individual categorical column.
        # Example:
        #  data = [39, 'State-gov', 77516, 'Bachelors', 13, 'Never-married', 'Adm-clerical',
        #         'Not-in-family', 'White', 'Male', 2174, 0, 40, 'United-States']
        #  scores = [0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        #
        # Returns: [['State-gov']]
        # Build the scores array.
        scores = [0] * len(COLUMNS[:-1])
        # This column is the categorical column we want to extract.
        scores[i] = 1
        skb = SelectKBest(k=1)
        skb.scores_ = scores
        # Convert the categorical column to a numerical value
        lbn = LabelBinarizer()
        r = skb.transform(train_features)
        lbn.fit(r)
        # Create the pipeline to extract the categorical feature
        categorical_pipelines.append(
            ('categorical-{}'.format(i), Pipeline([
                ('SKB-{}'.format(i), skb),
                ('LBN-{}'.format(i), lbn)])))
# [END categorical-feature-conversion]

# [START create-pipeline]
# Create pipeline to extract the numerical features
skb = SelectKBest(k=6)
# From COLUMNS use the features that are numerical
skb.scores_ = [1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 1, 1, 1, 0]
categorical_pipelines.append(('numerical', skb))

# Combine all the features using FeatureUnion
preprocess = FeatureUnion(categorical_pipelines)

# Create the classifier
classifier = RandomForestClassifier()

# Transform the features and fit them to the classifier
classifier.fit(preprocess.transform(train_features), train_labels)

# Create the overall model as a single pipeline
pipeline = Pipeline([
    ('union', preprocess),
    ('classifier', classifier)
])
# [END create-pipeline]

artifact_filename = 'model.joblib'
joblib.dump(pipeline, artifact_filename)

model_dir = os.getenv("AIP_MODEL_DIR")
storage_path = os.path.join(model_dir, artifact_filename)
blob = storage.blob.Blob.from_string(storage_path, client=gcs)
blob.upload_from_filename(artifact_filename)

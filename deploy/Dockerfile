# The API as a Lambda container image.
#
# A zip would be simpler, but numpy, pandas, pyarrow, scipy and statsmodels come
# to 382 MB unpacked against the 250 MB zip ceiling, so an image it is. The
# dependencies are installed before the source is copied, so editing the model
# reuses the cached layer and a deploy pushes megabytes rather than gigabytes.
FROM public.ecr.aws/lambda/python:3.12

COPY deploy/requirements-lambda.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements-lambda.txt

COPY applebee/ ${LAMBDA_TASK_ROOT}/applebee/
COPY web/ ${LAMBDA_TASK_ROOT}/web/
COPY deploy/regions.aws.json ${LAMBDA_TASK_ROOT}/regions.aws.json

# No inputs are baked in: the weather is read from S3 in byte ranges, so the
# image stays the same size whether the region is one state or thirteen.
CMD ["web.app.handler"]

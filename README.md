# FastAPI CI Pipeline

A small FastAPI service I built to practise CI properly rather than only
writing basic GitHub Actions workflows.

The main focus of this project was creating a pipeline that
automatically checks code quality, runs tests and only builds the Docker
image when those checks pass. I also created a custom composite action
for the Docker build so the build logic can be reused with different
image names or build contexts.

> Current stage: CI is implemented. CD is the next stage of the project.

## CI Flow

``` text
Push / Pull Request
        |
        v
   GitHub Actions
        |
   +----+----+
   |         |
   v         v
 Ruff      pytest
   |         |
   +----+----+
        |
    both pass
        |
        v
  Docker Build
```

Ruff and pytest run as separate jobs because they do not depend on each
other. The Docker job uses `needs` so it only runs after both validation
jobs succeed.

## Tech Stack

-   Python / FastAPI
-   pytest
-   Ruff
-   Docker
-   GitHub Actions
-   Git

## Project Structure

``` text
coderco-cicd/
├── .github/
│   ├── workflows/
│   │   └── ci.yml
│   └── actions/
│       └── docker-build/
│           └── action.yml
├── assignment1/
│   ├── app/
│   │   ├── __init__.py
│   │   └── main.py
│   ├── tests/
│   │   └── test_health.py
│   ├── Dockerfile
│   └── requirements.txt
├── .gitignore
└── README.md
```

## Application

The application is deliberately small because the main focus of the
project is the delivery pipeline.

It currently exposes:

``` text
GET /health
GET /version
```

`/health` returns:

``` json
{
  "status": "healthy"
}
```

I use the health endpoint in the automated test, and it also gives me
something I can later use for container/deployment health checks.

## Running Locally

From the repository:

``` bash
cd assignment1
python -m venv .venv
```

On Windows PowerShell:

``` powershell
.\.venv\Scripts\Activate.ps1
```

Install the dependencies:

``` bash
python -m pip install -r requirements.txt
```

Start the API:

``` bash
uvicorn app.main:app --reload
```

Then check:

``` text
http://localhost:8000/health
```

## Tests and Linting

Run the tests:

``` bash
python -m pytest tests -v
```

The current test sends a request to `/health` and checks that the API
returns HTTP 200 and the expected JSON response.

Run Ruff:

``` bash
python -m ruff check app tests
```

These are the same types of checks the CI pipeline runs automatically.

## Docker

Build the image from the repository root:

``` bash
docker build -t service-status-api assignment1
```

Run it:

``` bash
docker run -d --name status-api -p 8000:8000 service-status-api
```

The application can then be checked again through:

``` text
http://localhost:8000/health
```

## CI Design

I split linting and testing into separate jobs rather than making the
whole pipeline sequential.

``` text
        +--> lint ----+
        |             |
change -|             +--> docker-build
        |             |
        +--> test ----+
```

The Docker job depends on both:

``` yaml
needs:
  - lint
  - test
```

This means failed code does not continue to the Docker build stage.

For a project this small, one sequential job would be simpler and would
avoid repeating some runner setup. I kept them separate because it gives
clearer failure isolation and let me practise job dependencies and
parallel execution.

## Custom Docker Build Action

Instead of putting the Docker command directly in the workflow, I
created a local composite action:

``` text
.github/actions/docker-build/action.yml
```

The workflow passes values into it:

``` yaml
with:
  image-name: service-status-api
  context: assignment1
```

The action uses those inputs to run the Docker build.

This is probably more abstraction than a single Docker command needs,
but I wanted to understand how reusable actions and inputs work. It
would make more sense if the same build logic was being shared across
multiple services.

## Troubleshooting

The pipeline did not work first time. I tried to debug each problem from
the failed job rather than changing several things at once.

The process I used was:

``` text
Find failed job
      |
Read failed step/logs
      |
Identify exact error
      |
Compare CI with local setup
      |
Reproduce locally if possible
      |
Make one targeted change
      |
Test -> commit -> push
      |
Check the next CI run
```

### Ruff failed in CI

The first issue was the lint job failing with:

``` text
I001 - Import block is unsorted or unformatted
```

I checked the GitHub Actions logs first to find the exact job, step and
file causing the failure.

I then ran Ruff locally:

``` bash
cd assignment1
python -m ruff check app tests
```

During this I noticed I was running Ruff from `assignment1` locally,
while the CI command had been running from the repository root.

I changed the CI step to:

``` yaml
- name: Run Ruff linting
  working-directory: assignment1
  run: python -m ruff check app tests
```

This made the local and CI execution contexts consistent.

The main lesson from this was that when something works locally but
fails in CI, I should compare the environments rather than assuming the
code is the only difference. Working directory, dependency versions,
runtime version, environment variables and configuration can all change
behaviour.

### GitHub could not find my custom action

Once linting and tests were passing, the pipeline got further and
exposed another problem in the Docker job.

At first it looked like a Docker problem, but the logs showed that
`docker build` had not actually started. GitHub was failing while trying
to load the local action.

My workflow contained:

``` yaml
uses: ./.github/actions/docker-build
```

So I checked the repository structure.

GitHub expected:

``` text
.github/actions/docker-build/action.yml
```

but I had:

``` text
.github/actions/action.yml
```

I moved `action.yml` into the `docker-build` directory so the filesystem
matched the path used by the workflow.

That taught me to narrow a pipeline failure down before trying to fix
it. In this case Docker itself was fine; the problem was how GitHub
Actions resolved the local action path.

## Design Choices

### Parallel lint and test jobs

I kept these independent because neither needs the result of the other.

**Benefit:** clearer failures and the jobs can run at the same time.

**Trade-off:** each runner has to perform its own setup, so there is
some duplicated work.

### Docker after validation

The image is only built after linting and tests pass.

**Benefit:** there is no reason to package code that has already failed
required checks.

**Trade-off:** if a quality check is badly configured it can block the
build, so the checks themselves need to be maintained properly.

### Custom action

I used a composite action to make the Docker build configurable.

**Benefit:** the logic can be reused.

**Trade-off:** it adds another layer to understand and maintain. For one
build command, keeping it directly in the workflow would also be
reasonable.

## Current Limitations

This is currently a CI project, not a production-ready CI/CD platform.

The main gaps are:

-   small test suite
-   no container smoke test after the image is built
-   dependencies still need to be pinned to tested versions
-   no vulnerability scanning
-   image is not yet published to a registry
-   no staging or production deployment
-   no post-deployment health check
-   no monitoring or alerting
-   no rollback process

## What I Would Improve Next

The next version of the pipeline would move from only
validating/building the application to producing a traceable artifact
and delivering it somewhere.

My planned flow is:

``` text
Code Change
     |
     v
Lint + Tests
     |
     v
Docker Build
     |
     v
Container Smoke Test
     |
     v
Security Scan
     |
     v
Tag with Git SHA
     |
     v
Container Registry
     |
     v
Deployment
     |
     v
Health Verification
```

The first improvements I would make are:

1.  Pin the dependency versions that have been tested successfully.
2.  Add a smoke test that starts the built container and calls
    `/health`.
3.  Tag the Docker image with the Git commit SHA instead of relying on
    `latest`.
4.  Scan the image/dependencies before publishing.
5.  Push the validated image to GHCR or Amazon ECR.
6.  Add a real deployment stage and verify the application after
    deployment.
7.  Add logs, metrics and alerts once there is a runtime environment.

For a larger deployment I would also provision the infrastructure with
Terraform and document rollback/recovery steps.

## What I Learned

The biggest thing I took from this project was that CI is not just
writing YAML.

I had to understand how jobs depend on each other, how GitHub runners
execute commands, how working directories affect tools, how local custom
actions are resolved, and how to use logs to narrow down a failure.

The troubleshooting process was especially useful because the first
error was not the only error. Fixing Ruff allowed the pipeline to
progress far enough to expose the custom-action path problem.

Instead of treating a red pipeline as one big problem, I now approach it
as:

``` text
What failed?
      |
What evidence do the logs give me?
      |
Can I reproduce it?
      |
What is the smallest change that tests my theory?
      |
Did the next run prove the fix worked?
```

## Next Step

The next stage is CD.

I want to take the Docker image that has passed CI, give it an immutable
tag, publish it to a registry and then deploy that exact artifact to an
environment.

That will extend the current flow from:

``` text
Code -> Validate -> Build
```

to:

``` text
Code -> Validate -> Build -> Publish -> Deploy -> Verify
```

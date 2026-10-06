# FastAPI CI/CD Pipeline

A small FastAPI service I built to practise CI/CD properly rather than only writing basic GitHub Actions workflows.

The project started as a CI exercise and was extended into a full container delivery flow using GitHub Actions, Docker and Azure.

The main goal was to understand how code moves from validation to a versioned container artifact, how that artifact is published securely, and how the same artifact is deployed to a running environment.

---

## Current Stage

CI and CD are both implemented.

The current flow validates pull requests, protects `main`, builds and versions Docker images, authenticates to Azure using OIDC, pushes images to Azure Container Registry, and deploys the exact SHA-tagged image to Azure Container Apps.

---

## CI/CD Flow

```text
Feature Branch
    |
    v
Pull Request to main
    |
    +-------------------+
    |                   |
    v                   v
  Ruff                pytest
    |                   |
    +---------+---------+
              |
              v
      Docker build check
              |
              v
        Merge to main
              |
              v
      GitHub Actions
              |
              v
       Azure OIDC login
              |
              v
          ACR login
              |
              v
     Build + tag + push
              |
              v
 Azure Container Registry
              |
              v
   Azure Container Apps
              |
              v
       FastAPI runtime
```

---

## Tech Stack

- Python / FastAPI
- pytest
- Ruff
- Docker
- GitHub Actions
- Azure Container Registry
- Azure Container Apps
- Microsoft Entra ID
- GitHub OIDC
- Azure RBAC
- Git

---

## Project Structure

```text
coderco-cicd/
├── .github/
│   ├── workflows/
│   │   └── ci.yml
│   └── actions/
│       ├── docker-build/
│       │   └── action.yml
│       └── docker-publish/
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

---

## Application

The application is deliberately small because the focus is the delivery pipeline.

It exposes:

```text
GET /health
GET /version
```

`/health` returns:

```json
{
  "status": "healthy"
}
```

The health endpoint is used in automated testing and gives a simple runtime check once the container is deployed.

---

## Running Locally

From the repository:

```bash
cd assignment1
python -m venv .venv
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Start the API:

```bash
uvicorn app.main:app --reload
```

Check:

```text
http://localhost:8000/health
```

---

## Tests and Linting

Run tests:

```bash
python -m pytest tests -v
```

The current test sends a request to `/health` and checks for HTTP 200 and the expected JSON response.

Run Ruff:

```bash
python -m ruff check app tests
```

These are the same checks used in CI.

---

## Docker

Build locally from the repository root:

```bash
docker build -t service-status-api assignment1
```

Run the container:

```bash
docker run -d --name status-api -p 8000:8000 service-status-api
```

Then check:

```text
http://localhost:8000/health
```

---

## CI Design

Linting and testing run as separate jobs because they are independent.

```text
        +--> lint ----+
        |             |
change -|             +--> docker-build
        |             |
        +--> test ----+
```

The Docker validation job uses:

```yaml
needs:
  - lint
  - test
```

This prevents failed code from progressing to the Docker build check.

For a project this small, one sequential job would be simpler and would avoid duplicated runner setup. I kept linting and testing separate because it gave clearer failure isolation and let me practise parallel jobs and dependencies.

---

## Pull Request Controls

The repository uses branch protection on `main`.

Pull requests must pass:

- `lint`
- `test`
- `docker-build`

The Docker build job only runs on pull requests.

Its purpose is to prove that the application can still be packaged successfully before the change is merged.

Nothing is published to Azure from a pull request.

---

## Main Branch Release

Once code reaches `main`, the workflow follows a separate release path.

The release job:

1. authenticates GitHub Actions to Azure using OIDC
2. logs in to Azure Container Registry
3. builds the release image
4. tags the image with the Git commit SHA
5. pushes the image to ACR

The release image is therefore traceable back to the exact source commit that produced it.

Example:

```text
irshaadcicd.azurecr.io/service-status-api:<git-sha>
```

---

## Custom Docker Actions

### Docker Build Action

The pull request path uses:

```text
.github/actions/docker-build/action.yml
```

This action is intentionally small and only validates that the Docker image can build.

### Docker Publish Action

The release path uses:

```text
.github/actions/docker-publish/action.yml
```

This action handles:

```text
docker build
docker tag
docker push
```

I kept Azure authentication outside the composite action so the identity and permission flow stays visible in the main workflow.

That makes security-sensitive steps easier to review and troubleshoot.

---

## Artifact Strategy

One of the main design decisions was whether Docker build, tag and push should be split across separate GitHub Actions jobs.

Each GitHub job gets a fresh runner.

If I built the image in one job and tried to tag or push it in another, I would need to explicitly transfer the image between runners using a process such as:

```text
docker save
upload artifact
download artifact
docker load
```

That would work, but it would add:

- extra storage
- more network transfer
- longer pipeline time
- more workflow complexity
- another failure point

For this project, that complexity did not provide enough value.

I therefore kept the stateful Docker work together in one release job and used Azure Container Registry as the durable artifact store.

The release pattern is:

```text
validate
build once for release
tag with Git SHA
push to ACR
deploy that exact registry image
```

---

## Why the Image Is Tagged With the Git SHA

The release image is tagged using:

```yaml
image-tag: ${{ github.sha }}
```

This gives a direct mapping between:

```text
source commit
Docker image
ACR artifact
deployed container
```

Using only `latest` would make it harder to prove which code is actually running.

The SHA tag improves traceability, rollback and debugging.

---

## Azure Authentication With GitHub OIDC

I used GitHub OIDC instead of storing a long-lived Azure client secret in GitHub.

The flow is:

```text
GitHub Actions
    |
    v
GitHub issues OIDC token
    |
    v
Azure checks the federated identity rule
    |
    v
temporary Azure credentials
```

The federated identity is scoped to the GitHub repository and `main` branch.

This means Azure can verify which GitHub workflow context is requesting access without GitHub storing a permanent Azure password.

---

## Authentication vs Authorization

This project made the difference between authentication and authorization much clearer.

OIDC answers:

```text
Who is this workflow?
```

Azure RBAC answers:

```text
What is this identity allowed to do?
```

The GitHub Actions service principal is given permission to push images to ACR.

The Azure Container App uses managed identity with pull-only access to retrieve the image.

So the responsibilities are separated:

```text
GitHub Actions
= publish image

Azure Container App
= pull and run image
```

---

## Azure RBAC Troubleshooting

The first ACR push failed with:

```text
denied: requested access to the resource is denied
```

The Docker build and tag had succeeded, so the failure was not in Docker itself.

I checked the ACR role assignment and then the registry permission model.

The registry was using:

```text
RBAC Registry + ABAC Repository Permissions
```

while I had assigned the traditional `AcrPush` role.

For this project I switched the registry back to standard RBAC Registry Permissions so `AcrPush` matched the permission model I was using.

After that, the workflow successfully pushed the image.

The main lesson was to separate authentication, authorization and registry permission model instead of treating every push failure as a Docker or credential problem.

---

## Azure Container Registry

The final image is stored in:

```text
irshaadcicd.azurecr.io
```

Repository:

```text
service-status-api
```

The image is stored using the Git commit SHA as its tag.

This makes ACR the durable handoff point between the CI/CD pipeline and the runtime environment.

---

## Azure Container Apps Deployment

The image is deployed to Azure Container Apps using the exact SHA-tagged artifact already stored in ACR.

The deployment does not rebuild the image.

Container Apps pulls the existing artifact and runs the FastAPI service.

The container uses:

```text
Target port: 8000
Ingress: external
Transport: HTTP/Auto
```

The runtime uses managed identity with ACR pull access rather than registry admin credentials.

This keeps the runtime permission separate from the pipeline permission.

---

## Runtime Verification

After deployment, the application is verified using:

```text
/health
/version
```

The Container Apps environment also provides metrics and Log Analytics integration for runtime troubleshooting.

The service is running on the Consumption workload profile, so replicas can scale down when idle.

For this project I kept scale-to-zero enabled rather than forcing a minimum replica count.

---

## Troubleshooting Approach

The pipeline did not work first time.

I debugged each failure from the evidence rather than changing several things at once.

My process was:

```text
Find failed job
Read failed step and logs
Identify the exact error
Form a hypothesis
Make one targeted change
Commit and push
Check the next run
```

---

## Ruff Failed in CI

The lint job initially failed with:

```text
I001 - Import block is unsorted or unformatted
```

I checked the workflow logs and compared the CI execution context with local execution.

Locally I had been running Ruff from `assignment1`, while CI was running from the repository root.

I changed the CI step to:

```yaml
- name: Run Ruff linting
  working-directory: assignment1
  run: python -m ruff check app tests
```

That made the local and CI execution contexts consistent.

The lesson was that when something works locally but fails in CI, I should compare environments before assuming the code itself is the only difference.

---

## GitHub Could Not Find the Custom Action

After fixing Ruff, the pipeline progressed further and exposed another problem.

The workflow referenced:

```yaml
uses: ./.github/actions/docker-build
```

but the action file was not stored in the directory GitHub expected.

GitHub expected:

```text
.github/actions/docker-build/action.yml
```

I moved the file so the repository structure matched the workflow path.

This reinforced the value of narrowing a pipeline failure down to the exact stage before changing anything.

---

## Design Choices and Trade-offs

### Parallel lint and test jobs

Benefit:

- faster independent feedback
- clearer failure isolation

Trade-off:

- each job gets its own runner
- setup work is duplicated

### Docker build after validation

Benefit:

- failed code does not progress to packaging

Trade-off:

- required checks must be maintained correctly or they can block releases unnecessarily

### Composite actions

I used composite actions for repeated Docker logic.

Benefit:

- reusable logic
- cleaner workflow
- configurable inputs

Trade-off:

- another abstraction layer to understand and maintain

For one-off Azure authentication steps, keeping the commands visible in the main workflow was clearer than wrapping them in another custom action.

### Build and publish on the same runner

Benefit:

- no Docker image handoff between jobs
- fewer network transfers
- fewer failure points

Trade-off:

- build, tag and push are coupled inside one job

For this project, that was the simpler and more appropriate design.

---

## Current Limitations

The project is now a working CI/CD pipeline, but it is not a complete production platform.

Current gaps include:

- small test suite
- no container vulnerability scanning
- dependencies are not fully pinned
- no automated post-deployment smoke test from GitHub Actions
- no automated rollback
- no alerting
- no staging environment
- Container Apps deployment is currently configured manually rather than updated automatically from the workflow
- infrastructure is not yet provisioned through Terraform

---

## What I Would Improve Next

The next improvements would be:

1. Add a smoke test against the built container.
2. Add dependency and image vulnerability scanning.
3. Automate the Azure Container Apps deployment after ACR publish.
4. Verify `/health` automatically after deployment.
5. Add rollback using a previously known-good SHA-tagged image.
6. Add alerts around failed revisions or unhealthy responses.
7. Provision the Azure infrastructure through Terraform.

---

## What I Learned

The biggest lesson was that CI/CD is not just writing YAML.

I had to think about:

- which work should run in parallel
- when jobs should depend on each other
- what state disappears with a GitHub runner
- where artifacts should live
- when a composite action actually reduces complexity
- when abstraction makes troubleshooting harder
- how to separate authentication from authorization
- how to keep cloud credentials short-lived
- how to make a release artifact traceable to source code
- how to troubleshoot a pipeline from the exact failed stage

The most useful design lesson was that more jobs and more abstraction do not automatically make a pipeline better.

The goal is to use enough structure to make the release process reliable and understandable without adding unnecessary handoffs.

---

## Final Flow

```text
Code Change
    |
    v
Pull Request
    |
    v
Ruff + pytest
    |
    v
Docker Build Validation
    |
    v
Merge to main
    |
    v
GitHub OIDC Authentication
    |
    v
Build Release Image
    |
    v
Tag With Git SHA
    |
    v
Push to Azure Container Registry
    |
    v
Deploy Exact Image to Azure Container Apps
    |
    v
Verify Running FastAPI Service
```

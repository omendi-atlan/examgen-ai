import { expect, test, type Page, type Route } from "@playwright/test";

const workspaceId = "workspace-e2e";
const subjectId = "subject-inl201";
const resourceId = "resource-notes";
const versionId = "version-1";

const extractedResource = {
  id: resourceId,
  title: "INL201 lecture notes",
  subject_id: subjectId,
  visibility: "private",
  current_version_number: 1,
  versions: [{
    id: versionId,
    version_number: 1,
    original_filename: "lecture-notes.txt",
    extraction: {
      status: "extracted",
      character_count: 38,
      segment_count: 1,
      error_message: null,
    },
  }],
};

const failedResource = {
  ...extractedResource,
  id: "resource-failed",
  title: "Failed scan",
  versions: [{
    ...extractedResource.versions[0],
    id: "version-failed",
    extraction: {
      status: "failed",
      character_count: 0,
      segment_count: 0,
      error_message: "The OCR worker could not process this page.",
    },
  }],
};

async function mockCourseworkApi(page: Page) {
  const calls: { method: string; path: string }[] = [];
  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    calls.push({ method, path });

    if (path.endsWith("/auth/login") && method === "POST") {
      await route.fulfill({ json: { access_token: "e2e-student-token", token_type: "bearer" } });
      return;
    }
    if (path.endsWith("/workspaces") && method === "GET") {
      await route.fulfill({ json: [{ id: workspaceId, name: "Student Workspace", slug: "student-workspace" }] });
      return;
    }
    if (path.endsWith("/subjects") && method === "GET") {
      await route.fulfill({
        json: [{ id: subjectId, workspace_id: workspaceId, name: "INL201", description: "Information Systems", resource_sharing_enabled: false }],
      });
      return;
    }
    if (path.endsWith("/resources") && method === "GET") {
      await route.fulfill({ json: [extractedResource, failedResource] });
      return;
    }
    if (path.endsWith("/resources") && method === "POST") {
      await route.fulfill({ status: 201, json: extractedResource });
      return;
    }
    if (path.endsWith("/segments") && method === "GET") {
      await route.fulfill({
        json: [{ id: "segment-1", ordinal: 1, locator: "page:1", text: "Variables, functions and control flow.", metadata: {} }],
      });
      return;
    }
    if (path.endsWith("/download") && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "text/plain",
        headers: { "content-disposition": 'attachment; filename="lecture-notes.txt"', "cache-control": "private, no-store" },
        body: "Variables, functions and control flow.",
      });
      return;
    }
    if (path.endsWith("/retry") && method === "POST") {
      await route.fulfill({
        json: {
          ...failedResource,
          versions: [{
            ...failedResource.versions[0],
            extraction: { status: "queued", character_count: 0, segment_count: 0, error_message: null },
          }],
        },
      });
      return;
    }
    if (path.endsWith("/versions") && method === "POST") {
      await route.fulfill({
        status: 201,
        json: { ...extractedResource, current_version_number: 2 },
      });
      return;
    }
    await route.fulfill({ status: 404, json: { detail: `Unmocked E2E endpoint: ${method} ${path}` } });
  });
  return calls;
}

async function enterCoursework(page: Page) {
  await page.goto("/coursework");
  await page.getByLabel("Email").fill("student@example.test");
  await page.getByLabel("Password").fill("not-a-real-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Signed in. Choose your coursework workspace and subject.")).toBeVisible();
  await page.getByLabel("Workspace").selectOption(workspaceId);
  await page.getByLabel("Subject / module").selectOption(subjectId);
  await expect(page.getByRole("heading", { name: "Add a resource" })).toBeVisible();
}

test("student uploads, views, downloads and versions subject coursework resources", async ({ page }) => {
  const calls = await mockCourseworkApi(page);
  await enterCoursework(page);

  await expect(page.getByRole("button", { name: /INL201 lecture notes/ })).toBeVisible();
  await page.getByRole("button", { name: /INL201 lecture notes/ }).click();
  await expect(page.getByText("Variables, functions and control flow.")).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download original" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("lecture-notes.txt");

  await page.getByLabel("Append a revised version").setInputFiles({
    name: "lecture-notes-v2.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Revised coursework material."),
  });
  await page.getByRole("button", { name: "Add new version" }).click();
  await expect(page.getByRole("status")).toContainText("New immutable version added");
  expect(calls.some((call) => call.method === "POST" && call.path.endsWith("/versions"))).toBeTruthy();

  await page.getByLabel("Resource title").fill("Week 5 worksheet");
  await page.getByLabel("Upload a resource").setInputFiles({
    name: "worksheet.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Practice worksheet content."),
  });
  await page.getByRole("button", { name: "Upload to this subject" }).click();
  await expect(page.getByRole("status")).toContainText("Uploaded securely");
  expect(calls.some((call) => call.method === "POST" && call.path.endsWith("/resources"))).toBeTruthy();
});

test("student can retry a failed extraction without receiving cohort-sharing controls by default", async ({ page }) => {
  await mockCourseworkApi(page);
  await enterCoursework(page);

  await expect(page.getByRole("button", { name: /Failed scan/ })).toBeVisible();
  await page.getByRole("button", { name: /Failed scan/ }).click();
  await expect(page.getByText(/The OCR worker could not process this page/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry extraction" })).toBeVisible();
  await page.getByRole("button", { name: "Retry extraction" }).click();
  await expect(page.getByRole("status")).toContainText("safely requeued");
  await expect(page.getByLabel("Visibility")).not.toContainText("Share with enrolled cohort");
});

test("camera scanner captures a page and prepares a PDF for subject upload", async ({ page, context }) => {
  await context.grantPermissions(["camera"]);
  await mockCourseworkApi(page);
  await enterCoursework(page);

  await page.getByRole("button", { name: /Scan pages with camera/ }).click();
  const video = page.locator("video");
  await expect(video).toBeVisible();
  await expect.poll(async () => video.evaluate((element: HTMLVideoElement) => element.videoWidth)).toBeGreaterThan(0);

  await page.getByRole("button", { name: "Capture page" }).click();
  await expect(page.getByText("1 page(s) captured")).toBeVisible();
  await page.getByRole("button", { name: /Create PDF/ }).click();
  await expect(page.getByText(/Selected: coursework-scan-.*\.pdf/)).toBeVisible();
  await expect(page.getByRole("dialog", { name: "Document scanner" })).toHaveCount(0);
});

async function api(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.error || "Something went wrong.");
  }

  return data;
}

function formData(form) {
  return {
    name: form.elements.name.value,
    description: form.elements.description.value,
    subject: form.elements.subject.value,
    credits: Number(form.elements.credits.value)
  };
}

async function showCourses() {
  const list = document.querySelector("#course-list");
  if (!list) return;

  try {
    const courses = await api("/api/courses");
    list.replaceChildren();

    if (courses.length === 0) {
      list.textContent = "No courses have been added yet.";
      return;
    }

    for (const course of courses) {
      const card = document.createElement("article");
      card.className = "course-card";

      const title = document.createElement("h3");
      title.textContent = course.name;

      const subject = document.createElement("p");
      subject.textContent = `Subject: ${course.subject}`;

      const credits = document.createElement("p");
      credits.textContent = `Credits: ${course.credits}`;

      const description = document.createElement("p");
      description.textContent = course.description;

      const link = document.createElement("a");
      link.href = `course-details.html?id=${course.id}`;
      link.textContent = "View Course";

      card.append(title, subject, credits, description, link);
      list.append(card);
    }
  } catch (error) {
    list.textContent = error.message;
  }
}

function setupAddForm() {
  const form = document.querySelector("#add-course-form");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    try {
      const result = await api("/api/courses", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData(form))
      });

      window.location.href = `course-details.html?id=${result.id}`;
    } catch (error) {
      document.querySelector("#message").textContent = error.message;
    }
  });
}

async function setupDetails() {
  const form = document.querySelector("#edit-course-form");
  if (!form) return;

  const id = new URLSearchParams(window.location.search).get("id");
  const message = document.querySelector("#message");

  if (!id || !/^\d+$/.test(id)) {
    message.textContent = "No course was selected.";
    form.hidden = true;
    return;
  }

  try {
    const course = await api(`/api/courses/${id}`);
    form.elements.name.value = course.name;
    form.elements.description.value = course.description;
    form.elements.subject.value = course.subject;
    form.elements.credits.value = course.credits;
  } catch (error) {
    message.textContent = error.message;
    form.hidden = true;
    return;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    try {
      await api(`/api/courses/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData(form))
      });
      message.textContent = "Course saved.";
    } catch (error) {
      message.textContent = error.message;
    }
  });

  document.querySelector("#delete-course").addEventListener("click", async () => {
    if (!confirm("Delete this course?")) return;

    try {
      await api(`/api/courses/${id}`, { method: "DELETE" });
      window.location.href = "courses.html";
    } catch (error) {
      message.textContent = error.message;
    }
  });
}

showCourses();
setupAddForm();
setupDetails();

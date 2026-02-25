function openEditModal(
  id,
  usn,
  name,
  email,
  phone,
  studentClass,
  department,
  parentName,
  parentPhone,
  parentEmail,
) {
  const modal = document.getElementById("editModal");
  const form = document.getElementById("editForm");
  form.action = `/students/edit/${id}`;
  document.getElementById("edit_usn").value = usn;
  document.getElementById("edit_name").value = name;
  document.getElementById("edit_email").value = email;
  document.getElementById("edit_phone").value = phone || "";
  document.getElementById("edit_class").value = studentClass;
  document.getElementById("edit_department").value = department;
  document.getElementById("edit_parent_name").value = parentName || "";
  document.getElementById("edit_parent_phone").value = parentPhone || "";
  document.getElementById("edit_parent_email").value = parentEmail || "";
  modal.style.display = "block";
}

function closeEditModal() {
  document.getElementById("editModal").style.display = "none";
}

// Close modal when clicking outside
window.onclick = function (event) {
  const modal = document.getElementById("editModal");
  if (event.target === modal) {
    modal.style.display = "none";
  }
};

// Auto-hide flash messages
document.addEventListener("DOMContentLoaded", function () {
  const alerts = document.querySelectorAll(".alert");
  alerts.forEach((alert) => {
    setTimeout(() => {
      alert.style.transition = "opacity 0.5s";
      alert.style.opacity = "0";
      setTimeout(() => alert.remove(), 500);
    }, 3000);
  });
});

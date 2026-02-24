/* =========================
    GLOBAL LOADER
========================= */

function showLoader() {
    document.getElementById("globalLoader").style.display = "flex";
}

function hideLoader() {
    document.getElementById("globalLoader").style.display = "none";
}

/* Auto loader on form submit */
document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("form").forEach(form => {
        form.addEventListener("submit", () => showLoader());
    });
});


/* =========================
    CONFIRMATION MODAL
========================= */

function openConfirmModal(message, callback) {
    const modal = document.getElementById("confirmModal");
    const msgBox = document.getElementById("confirmMessage");
    const confirmBtn = document.getElementById("confirmActionBtn");

    msgBox.innerText = message;
    modal.style.display = "flex";

    confirmBtn.onclick = function () {
        modal.style.display = "none";
        callback();
    };
}

function closeConfirmModal() {
    document.getElementById("confirmModal").style.display = "none";
}


/* =========================
    BUTTON HELPERS
========================= */

function confirmDelete(url) {
    openConfirmModal("Are you sure you want to delete this item?", () => {
        window.location.href = url;
    });
}

function confirmSave(formId) {
    openConfirmModal("Save changes?", () => {
        document.getElementById(formId).submit();
    });
}

function confirmUpdate(formId) {
    openConfirmModal("Update this record?", () => {
        document.getElementById(formId).submit();
    });
}
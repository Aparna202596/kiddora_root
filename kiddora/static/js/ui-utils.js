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
// Delete confirmation
function confirmDelete(url) {
    openConfirmModal("Are you sure you want to delete this item?", () => {
        window.location.href = url;
    });
}
// Save confirmation
function confirmSave(formId) {
    openConfirmModal("Confirm Save?", () => {
        document.getElementById(formId).submit();
    });
}
// Update confirmation
function confirmUpdate(formId) {
    openConfirmModal("Update this record?", () => {
        document.getElementById(formId).submit();
    });
}
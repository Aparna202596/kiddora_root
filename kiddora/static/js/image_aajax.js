export function ajaxUpload(formSelector, url) {
    const form = document.querySelector(formSelector);

    form.addEventListener("submit", async e => {
        e.preventDefault();

        const formData = new FormData(form);

        const res = await fetch(url, {
            method: "POST",
            body: formData,
            headers: {"X-Requested-With": "XMLHttpRequest"}
        });

        const data = await res.json();

        if (data.status === "success") {
            alert("Image updated!");
            location.reload();
        } else {
            alert(data.message);
        }
    });
}

class ImageUploader {
    constructor({input, preview, dropzone, form, cropInput}) {
        this.input = document.querySelector(input);
        this.preview = document.querySelector(preview);
        this.dropzone = document.querySelector(dropzone);
        this.form = document.querySelector(form);
        this.cropInput = document.querySelector(cropInput);
        this.cropper = null;

        this.init();
    }

    init() {
        if (this.input) {
            this.input.addEventListener("change", e => this.showPreview(e.target.files[0]));
        }

        if (this.dropzone) {
            this.dropzone.addEventListener("dragover", e => {
                e.preventDefault();
                this.dropzone.classList.add("dragover");
            });

            this.dropzone.addEventListener("dragleave", () => {
                this.dropzone.classList.remove("dragover");
            });

            this.dropzone.addEventListener("drop", e => {
                e.preventDefault();
                this.dropzone.classList.remove("dragover");
                const file = e.dataTransfer.files[0];
                this.input.files = e.dataTransfer.files;
                this.showPreview(file);
            });
        }

        if (this.form) {
            this.form.addEventListener("submit", e => this.handleSubmit(e));
        }
    }

    showPreview(file) {
        if (!file) return;

        const reader = new FileReader();
        reader.onload = () => {
            this.preview.src = reader.result;

            if (this.cropper) this.cropper.destroy();
            this.cropper = new Cropper(this.preview, {aspectRatio: 1});
        };
        reader.readAsDataURL(file);
    }

    handleSubmit(e) {
        if (!this.cropper) return;

        const data = this.cropper.getData();
        this.cropInput.value = JSON.stringify(data);
    }
}

export default ImageUploader;

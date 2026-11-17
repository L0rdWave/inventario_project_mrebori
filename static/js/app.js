document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) {
        return;
    }

    const openButton = target.closest("[data-dialog-open]");
    if (openButton instanceof HTMLButtonElement) {
        const dialogId = openButton.getAttribute("data-dialog-open");
        const dialog = dialogId ? document.getElementById(dialogId) : null;
        if (dialog instanceof HTMLDialogElement) {
            dialog.showModal();
        }
        return;
    }

    const closeButton = target.closest("[data-dialog-close]");
    const dialog = closeButton ? closeButton.closest("dialog") : null;
    if (dialog instanceof HTMLDialogElement) {
        dialog.close();
    }
});

document.addEventListener("DOMContentLoaded", function () {
    console.log("InterviewMate AI is running!");

    const textareas = document.querySelectorAll("textarea");

    textareas.forEach(function (textarea) {
        textarea.addEventListener("input", function () {
            console.log("Answer is being typed.");
        });
    });
});
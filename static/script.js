document.addEventListener("DOMContentLoaded", function () {
    const answerField = document.querySelector("#answer");
    const wordCount = document.querySelector("#word-count");
    if (answerField && wordCount) {
        function updateWordCount() {
            const words = answerField.value.trim().match(/\S+/g) || [];
            wordCount.textContent = `${words.length} ${words.length === 1 ? "word" : "words"}`;
        }

        answerField.addEventListener("input", updateWordCount);
        updateWordCount();
    }

    const speakButton = document.querySelector("#speak-question");
    const voiceStatus = document.querySelector("#voice-status");
    const audioPlayer = document.querySelector("#question-audio");
    if (!speakButton || !voiceStatus || !audioPlayer) {
        return;
    }

    let audioUrl;
    speakButton.addEventListener("click", async function () {
        speakButton.disabled = true;
        voiceStatus.textContent = "Preparing your question...";

        try {
            const response = await fetch(speakButton.dataset.audioUrl, {
                method: "POST",
                headers: { "X-Requested-With": "XMLHttpRequest" }
            });
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || "Could not generate question audio.");
            }

            const audioBlob = await response.blob();
            if (audioUrl) {
                URL.revokeObjectURL(audioUrl);
            }
            audioUrl = URL.createObjectURL(audioBlob);
            audioPlayer.src = audioUrl;
            audioPlayer.hidden = false;
            audioPlayer.load();

            try {
                await audioPlayer.play();
                voiceStatus.textContent = "Playing your question...";
            } catch {
                voiceStatus.textContent = "Audio is ready. Press play to hear the question.";
            }
        } catch (error) {
            voiceStatus.textContent = error.message || "Could not generate question audio.";
        } finally {
            speakButton.disabled = false;
        }
    });

    audioPlayer.addEventListener("ended", function () {
        voiceStatus.textContent = "Question audio finished.";
    });
});
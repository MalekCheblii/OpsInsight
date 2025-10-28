
import styles from "./messageList.module.css";
import { useState } from "react";

const MessageList = () => {
    
    const [userMessage, setUserMessage] = useState("");
    const [chatHistory, setChatHistory] = useState([]);
    const [isLoading, setIsLoading] = useState(false);
    const [imageFile, setImageFile] = useState(null);
    const sendMessage = async () => {
        if (!userMessage.trim()) return;
        setIsLoading(true);
        try {
            const FormData = new FormData();
            FormData.append("prompt", userMessage);
            if (imageFile) {
                FormData.append("file", imageFile);
            }
            const response = await fetch("http://127.0.0.1:8000/uploadfile/", {
                method: "POST",
                body: FormData,
            });
            if (!response.ok) {
                throw new Error("Failed to fetch response from server");
            }
            const data = await response.json();
            if (imageFile) 
                setChatHistory((prev) => [
                    ...prev,
                    { sender: "user", message: userMessage, isImage: false },
                    { sender: "user", message: userMessage, isImage: true },
                    { sender: "bot", message: data.response, isImage: false },
                ]);
            else {
                setChatHistory((prev) => [
                    ...prev,
                    { sender: "user", message: userMessage, isImage: false },
                    { sender: "bot", message: data.response, isImage: false },
                ]);

            }
            setUserMessage("");
            setImageFile(null);

        } 
        catch (error) {
            console.error("Error sending message:", error);
            alert("Failed to send message. Please try again.");
        } finally {
            setIsLoading(false);
        }
    };

    const handleImageUpload = (e) => {
        const file = e.target.files[0];
        if (file) {
            setImageFile(file);
        }
    };

    return (
        <div className={styles.container}>
            <h1 className={styles.header}>Chat with OpsInsight Assitant !</h1>
            <div className={styles.chatbox}>
                {chatHistory.map((chat, index) => (
                    <div key={index} className={`${styles.message} ${chat.sender === "user" ? styles.userMessage : styles.botMessage}`}>
                         {
                         chat.isImage ? (
                            <img
                                src={URL.createObjectURL(chat.message)}
                                alt="Uploaded"
                                className={styles.image}
                            />
                         ) : (
                             chat.message
                         )}
                    </div>
                ))}
            </div>
            <div className={styles.inputContainer}>
                <input 
                    type="text" 
                    placeholder="Type your message here..." 
                    className={styles.input} 
                    value={userMessage} 
                    onChange={(e) => setUserMessage(e.target.value)}
                    disabled={isLoading}
                />
                <label htmlFor="image-upload" className={styles.paperclipButton}>📎
                </label>
                <input 
                    id = "image-upload"
                    type="file"
                    accept="image/*"
                    className={styles.inputImage}
                    onChange={handleImageUpload}
                />
                <button 
                    onClick={sendMessage} 
                    className={styles.button}
                    disabled={!userMessage.trim() || isLoading}
                >
                    {isLoading ? "Sending..." : "Send"}
                </button>
            </div>
        </div>
    );
};

export default MessageList;
// Import the functions you need from the SDKs you need
import { initializeApp } from "firebase/app";
import { getFirestore, collection, addDoc, getDocs, query, where, orderBy, serverTimestamp, deleteDoc } from "firebase/firestore";

// Your web app's Firebase configuration
const firebaseConfig = {
  apiKey: "your_firebase_api_key_here",
  authDomain: "internai-53d33.firebaseapp.com",
  projectId: "internai-53d33",
  storageBucket: "internai-53d33.firebasestorage.app",
  messagingSenderId: "583547745481",
  appId: "1:583547745481:web:a6a4fd9dc60e5bdfc54918"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);

// Initialize Firestore
export const db = getFirestore(app);

// Chat storage functions
export const saveChatMessage = async (userId, message) => {
  try {
    const chatData = {
      userId,
      type: message.type,
      content: message.content,
      timestamp: serverTimestamp(),
      data: message.data || null,
      fileInfo: message.fileInfo || null
    };

    const docRef = await addDoc(collection(db, "chats"), chatData);
    return docRef.id;
  } catch (error) {
    throw error;
  }
};

export const loadChatHistory = async (userId) => {
  try {
    const chatsRef = collection(db, "chats");
    const q = query(
      chatsRef,
      where("userId", "==", userId),
      orderBy("timestamp", "asc")
    );
    
    const querySnapshot = await getDocs(q);
    const messages = [];
    
    querySnapshot.forEach((doc) => {
      const data = doc.data();
      messages.push({
        id: doc.id,
        type: data.type,
        content: data.content,
        timestamp: data.timestamp?.toDate()?.toLocaleTimeString() || new Date().toLocaleTimeString(),
        data: data.data,
        fileInfo: data.fileInfo
      });
    });

    return messages;
  } catch (error) {
    return [];
  }
};

export const clearUserChatHistory = async (userId) => {
  try {
    const chatsRef = collection(db, "chats");
    const q = query(chatsRef, where("userId", "==", userId));
    const querySnapshot = await getDocs(q);
    
    const deletePromises = [];
    querySnapshot.forEach((doc) => {
      deletePromises.push(deleteDoc(doc.ref));
    });
    
    await Promise.all(deletePromises);
  } catch (error) {
    throw error;
  }
}; 
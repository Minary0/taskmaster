// ===== server.js =====
import express from "express";
import { createServer } from "http";
import { Server } from "socket.io";

const app = express();
const httpServer = createServer(app);
const io = new Server(httpServer, { cors: { origin: "*" } });

io.on("connection", (socket) => {
  console.log("🟢 Connecté :", socket.id);

  socket.on("joinRoom", (roomId) => {
    socket.join(roomId);
    console.log(`👥 ${socket.id} a rejoint ${roomId}`);
  });

  socket.on("signal", ({ roomId, data }) => {
    socket.to(roomId).emit("signal", { id: socket.id, data });
  });

  socket.on("disconnect", () => {
    console.log("🔴 Déconnecté :", socket.id);
  });
});

const PORT = process.env.PORT || 3001;
httpServer.listen(PORT, () => {
  console.log(`🚀 Serveur Socket.io prêt sur le port ${PORT}`);
});

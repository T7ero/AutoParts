import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Navbar from './components/Navbar';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Upload from './pages/Upload';
import Tasks from './pages/Tasks';
import Results from './pages/Results';
import Logs from './pages/Logs';

function App() {
  return (
    <Router>
      <div className="min-h-screen bg-gray-100">
        <Navbar />
        <main className="container mx-auto px-4 py-8">
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<Dashboard />} />
            <Route path="/upload" element={<Upload />} />
            <Route path="/tasks" element={<Tasks />} />
            <Route path="/results" element={<Results />} />
            <Route path="/logs" element={<Logs />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App; 
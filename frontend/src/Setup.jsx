// frontend/src/Setup.jsx
import React, { useState } from 'react';

function Setup({ onStart }) {
  // State for the form selections
  const [difficulty, setDifficulty] = useState('Medium');
  const [topic, setTopic] = useState('Array'); // Default to a valid topic
  const [persona, setPersona] = useState('Neutral');

  const handleSubmit = (e) => {
    e.preventDefault();
    onStart({ difficulty, topic, persona });
  };

  return (
    <div style={styles.overlay}>
      <div style={styles.card}>
        <h1 style={styles.title}>AI Mock Interviewer</h1>
        <p style={styles.subtitle}>Configure your session</p>
        
        <form onSubmit={handleSubmit} style={styles.form}>
          
          {/* 1. Difficulty */}
          <div style={styles.field}>
            <label style={styles.label}>Difficulty</label>
            <select style={styles.input} value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
              <option value="Easy">Easy</option>
              <option value="Medium">Medium</option>
              <option value="Hard">Hard</option>
            </select>
          </div>

          {/* 2. Topic (Matches your Database) */}
          <div style={styles.field}>
            <label style={styles.label}>Topic</label>
            <select style={styles.input} value={topic} onChange={(e) => setTopic(e.target.value)}>
              <option value="Array">Array</option>
              <option value="String">String</option>
              <option value="Tree">Tree</option>
              <option value="Dynamic Programming">Dynamic Programming</option>
              <option value="Math">Math</option>
              <option value="Hash Table">Hash Table</option>
              <option value="Linked List">Linked List</option>
            </select>
          </div>

          {/* 3. Persona */}
          <div style={styles.field}>
            <label style={styles.label}>Interviewer Persona</label>
            <select style={styles.input} value={persona} onChange={(e) => setPersona(e.target.value)}>
              <option value="Neutral">Neutral</option>
              <option value="Friendly">Friendly</option>
              <option value="Strict">Strict</option>
            </select>
          </div>

          <button type="submit" style={styles.button}>Start Interview</button>
        </form>
      </div>
    </div>
  );
}

// STYLES (Updated for centering and size)
const styles = {
  overlay: { 
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    width: '100vw', 
    height: '100vh', 
    display: 'flex', 
    justifyContent: 'center', // Horizontal Center
    alignItems: 'center',     // Vertical Center
    backgroundColor: '#121212', 
    color: 'white',
    zIndex: 1000,
    margin: 0,
    padding: 0
  },
  card: { 
    backgroundColor: '#1e1e1e', 
    padding: '60px',            // Big padding
    borderRadius: '20px', 
    boxShadow: '0 10px 40px rgba(0,0,0,0.6)', 
    width: '600px',             // WIDER card
    maxWidth: '90%',
    display: 'flex',
    flexDirection: 'column'
  },
  title: { 
    textAlign: 'center', 
    marginBottom: '10px',
    fontSize: '42px',           // HUGE Title
    fontWeight: 'bold',
    marginTop: 0
  },
  subtitle: { 
    textAlign: 'center', 
    color: '#aaa', 
    marginBottom: '50px',
    fontSize: '20px' 
  },
  form: { 
    display: 'flex', 
    flexDirection: 'column', 
    gap: '30px' 
  },
  field: { 
    display: 'flex', 
    flexDirection: 'column', 
    gap: '12px' 
  },
  label: { 
    fontSize: '25px',           // BIGGER labels
    fontWeight: '600', 
    color: '#e0e0e0' 
  },
  input: { 
    padding: '16px', 
    borderRadius: '8px', 
    border: '2px solid #333', 
    backgroundColor: '#2d2d2d', 
    color: 'white', 
    fontSize: '25px',           // BIGGER Text inside box
    cursor: 'pointer',
    outline: 'none'
  },
  button: { 
    padding: '20px', 
    marginTop: '20px', 
    borderRadius: '10px', 
    border: 'none', 
    backgroundColor: '#4caf50', 
    color: 'white', 
    fontSize: '25px',           // BIGGER button text
    cursor: 'pointer', 
    fontWeight: 'bold',
    textTransform: 'uppercase',
    letterSpacing: '1px'
  }
};

export default Setup;
import { styled } from 'styled-components'

export const InputField = styled.input`
  margin: 8px 0 8px 0;
  width: 70%;
  padding: 6px;
  border-radius: 4px;
  border: none;
  background-color: #ddd;
  color: #333;
  box-shadow: 1px 1px 2px white;
  transition: all 0.2s ease;

  &:focus {
    transform: scale(1.02);
    outline: none;
    border: 1px solid #ddd;
  }
`

# Pointer Safety Reference Details

## Dog Tag Fields Technique

Dog tag fields are validation markers placed in memory structures to detect corruption:

```cpp
struct SafeBlock {
    int dog_tag;  // Magic number for validation
    int data;
    int end_tag;  // Another marker
};

bool is_valid(SafeBlock* block) {
    return block && 
           block->dog_tag == 0xDEADBEEF && 
           block->end_tag == 0xBEEFDEAD;
}
```

## Memory Parachute Technique

The memory parachute provides a safety buffer for critical operations:

```cpp
void critical_operation(char* buffer, size_t size) {
    // Allocate extra space as "parachute"
    char* safe_buffer = new char[size + PARACHUTE_SIZE];
    
    // Initialize parachute with known pattern
    memset(safe_buffer + size, 0xAA, PARACHUTE_SIZE);
    
    // Perform operation
    // ...
    
    // Check if parachute was touched (buffer overflow)
    for (size_t i = size; i < size + PARACHUTE_SIZE; i++) {
        if (safe_buffer[i] != 0xAA) {
            // Buffer overflow detected!
            handle_error();
            break;
        }
    }
    
    delete[] safe_buffer;
}
```

## Smart Pointer Comparison

| Type | Ownership | Copyable | Use Case |
|------|-----------|----------|----------|
| `std::unique_ptr` | Exclusive | No | Single owner, automatic cleanup |
| `std::shared_ptr` | Shared | Yes | Multiple owners, reference counting |
| `std::weak_ptr` | Observer | Yes | Break circular references |

## SAFE_ Routine Example

```cpp
// Safe wrapper for memory operations
template<typename T>
T* safe_allocate(size_t count) {
    T* ptr = new (std::nothrow) T[count];
    if (ptr == nullptr) {
        throw std::bad_alloc();
    }
    return ptr;
}

template<typename T>
void safe_free(T*& ptr) {
    if (ptr != nullptr) {
        delete[] ptr;
        ptr = nullptr;
    }
}
```

## Linked List Safe Deletion

```cpp
void safe_delete_node(Node** head_ref, int key) {
    if (head_ref == nullptr || *head_ref == nullptr) {
        return;
    }
    
    Node* temp = *head_ref;
    Node* prev = nullptr;
    
    // If head node holds the key
    if (temp->data == key) {
        *head_ref = temp->next;
        delete temp;
        temp = nullptr;  // Prevent dangling pointer
        return;
    }
    
    // Search for the node
    while (temp != nullptr && temp->data != key) {
        prev = temp;
        temp = temp->next;
    }
    
    // If key was not present
    if (temp == nullptr) {
        return;
    }
    
    // Unlink the node
    prev->next = temp->next;
    delete temp;
    temp = nullptr;  // Prevent dangling pointer
}
```

## Common Memory Corruption Patterns

1. **Use After Free**: Accessing memory after it's been deallocated
2. **Double Free**: Freeing the same memory twice
3. **Buffer Overflow**: Writing past allocated memory bounds
4. **Dangling Pointer**: Pointer to freed or out-of-scope memory
5. **Memory Leak**: Failing to free allocated memory
6. **Uninitialized Pointer**: Using pointer without initialization
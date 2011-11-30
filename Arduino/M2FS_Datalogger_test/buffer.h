







#define MAX_RECORD_SIZE_BYTES 245  //Must be >= 200+4*n_temp_sens+sizeof(buffsize_t)
#define buffsize_t uint8_t         //written assuming buffer is <256
#define BUFFER_SIZE MAX_RECORD_SIZE_BYTES
uint8_t thebuffer[MAX_RECORD_SIZE_BYTES+sizeof(buffsize_t)];


inline void bufferRewind();

inline buffsize_t bufferPos();

inline uint8_t* bufferGetBufPtr();

inline boolean bufferIsEmpty();

inline uint8_t* bufferWritePtr();

inline void bufferIncrementWritePtr(buffsize_t amt);

void bufferPut(void * data, buffsize_t n_bytes);

void bufferPut(uint8_t data);

inline buffsize_t bufferSpaceRemaining();



//Returns pointer to the complete record
inline uint8_t* bufferGetRecordPtr() {
	return thebuffer;
}

inline uint8_t bufferGetRecordSize() {
	return thebuffer[0]+1;
}



inline void bufferRewind(){
//        Serial.println("#Rewinding buffer");
	thebuffer[0]=0;
}

inline buffsize_t bufferPos(){
	return thebuffer[0];
}

//Returns pointer to the data portion of the record
inline uint8_t* bufferGetBufPtr() {
	return thebuffer+1;
}

inline boolean bufferIsEmpty() {
	return thebuffer[0]==0;
}

inline uint8_t* bufferWritePtr() {
	return thebuffer+thebuffer[0]+1;
}

//NO BOUNDS CHECKING
inline void bufferIncrementWritePtr(buffsize_t amt) {
	thebuffer[0]+=amt;
}

void bufferPut(void * data, buffsize_t n_bytes){
	if (n_bytes > bufferSpaceRemaining() ) {
		memcpy(bufferWritePtr(), data, bufferSpaceRemaining() );
		bufferIncrementWritePtr(bufferSpaceRemaining());
                Serial.print("#Buffer Overflew!\n");
	}
/*	else if (bufferIsEmpty()) {
                bufferPut('!');bufferPut('!');
                bufferPut(data, n_bytes);
        }*/
        else {
//                Serial.print("#Insert ");Serial.println(n_bytes,DEC);
		memcpy(bufferWritePtr(), data, n_bytes);
		bufferIncrementWritePtr(n_bytes);
	}
}

void bufferPut(uint8_t data){
	if (bufferSpaceRemaining() > 0) {
		*(bufferWritePtr())=data;
		bufferIncrementWritePtr(1);
	}	
}
/*
void bufferPut(uint8_t data){
	if (bufferSpaceRemaining() > 0)
		thebuffer[thebuffer[0]++]=data;
}
*/

inline buffsize_t bufferSpaceRemaining() {
	return BUFFER_SIZE - thebuffer[0];
}
